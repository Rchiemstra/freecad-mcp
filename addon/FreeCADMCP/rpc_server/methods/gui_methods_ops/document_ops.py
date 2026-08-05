"""Document listing and open/reload RPC methods (Phase 4 slice 4G)."""

from __future__ import annotations

import logging
from typing import Any

from .collaboration_context_core import (
    _member,
    activate_personal_target,
    request_actor,
)
from .collaboration_context_dispatch import dispatch_gui, public_error
from .collaboration_context_view import build_view_context

logger = logging.getLogger("FreeCADMCP.rpc_server")


class _DocumentOpenRejectedError(RuntimeError):
    error_code = "DUPLICATE_OR_INVALID_DOCUMENT_OPEN"


class _DocumentOpenIdentityRejectedError(RuntimeError):
    error_code = "DOCUMENT_OPEN_IDENTITY_REJECTED"


def _close_rejected_open(collaborators, document_name, existing_names):
    if not document_name or document_name in existing_names:
        return
    collaborators.freecad.closeDocument(document_name)


def _note_secondary(primary, label, callback):
    try:
        callback()
    except Exception as secondary:
        primary.add_note(f"{label} also failed: {secondary}")


def _restore_failed_reload(collaborators, doc_name, actor, prior, result):
    if prior is None:
        return
    try:
        collaborators.restore_personal_view_context(doc_name, actor, prior)
    except Exception as restore_error:
        diagnostic = collaborators.redact_rpc_diagnostic(restore_error)
        logger.error(
            "Personal view restore failed after reload rejection: %s", diagnostic
        )
    return result


def _complete_open(facade, result, actor, existing_names):
    collaborators = facade._gui_collaborators
    document_name = str(result.get("document") or "")
    prior_context = None
    context_may_have_changed = False
    try:
        document = collaborators.freecad.getDocument(document_name)
        if document is None:
            raise RuntimeError("opened document proxy is unavailable")
        prior_context = collaborators.snapshot_personal_view_context(
            document_name, actor
        )
        identity = collaborators.ensure_v2_document(document)
        result["document_session_uuid"] = identity.session_uuid
        result["canonical_path"] = identity.canonical_path
        context = build_view_context(facade, document, actor)
        context_may_have_changed = True
        _member(collaborators, "store_personal_view_context")(
            document_name, actor, context
        )
        activate_personal_target(facade, actor, document)
        return result
    except Exception as exc:
        if context_may_have_changed:
            _note_secondary(
                exc,
                "actor context rollback",
                lambda: collaborators.restore_personal_view_context(
                    document_name, actor, prior_context
                ),
            )
        _note_secondary(
            exc,
            "rejected-open cleanup",
            lambda: _close_rejected_open(collaborators, document_name, existing_names),
        )
        collaborators.reraise_if_cancelled(exc)
        raise _DocumentOpenIdentityRejectedError(str(exc)) from exc


def _open_checked(facade, path):
    collaborators = facade._gui_collaborators
    existing_names = set(collaborators.freecad.listDocuments())
    identity_service = collaborators.document_identity_service
    if identity_service is not None:
        try:
            identity_service.assert_open_path_available(path)
        except Exception as exc:
            collaborators.reraise_if_cancelled(exc)
            raise _DocumentOpenRejectedError(str(exc)) from exc
    actor = request_actor(facade)
    result = collaborators.open_document(path)
    if not isinstance(result, dict) or not result.get("ok"):
        return result
    return _complete_open(facade, result, actor, existing_names)


def list_documents(self):
    collaborators = self._gui_collaborators
    res = dispatch_gui(self, lambda: list(collaborators.freecad.listDocuments().keys()))
    return res if isinstance(res, list) else []


def reload_document(self, doc_name: str) -> dict[str, Any]:
    collaborators = self._gui_collaborators
    try:
        actor = request_actor(self)

        def reload_checked():
            prior = collaborators.snapshot_personal_view_context(doc_name, actor)
            try:
                result = collaborators.reload_document(doc_name)
                document = collaborators.freecad.getDocument(doc_name)
                succeeded = result is True or (
                    isinstance(result, dict)
                    and bool(result.get("ok") or result.get("success"))
                )
                if not succeeded:
                    _restore_failed_reload(
                        collaborators, doc_name, actor, prior, result
                    )
                    return result
                if prior is not None:
                    collaborators.restore_personal_view_context(doc_name, actor, prior)
                if document is not None:
                    if prior is None:
                        context = build_view_context(self, document, actor)
                        collaborators.store_personal_view_context(
                            doc_name, actor, context
                        )
                    activate_personal_target(self, actor, document)
                return result
            except Exception as exc:
                _note_secondary(
                    exc,
                    "personal view restore",
                    lambda: collaborators.restore_personal_view_context(
                        doc_name, actor, prior
                    ),
                )
                raise

        def reload_public_result():
            return self._adapt_gui_mutation_result(
                reload_checked(), success_fields={"document_name": doc_name}
            )

        res = dispatch_gui(self, reload_public_result)
    except Exception as exc:
        return public_error(self, exc)
    return res


def open_document(self, path: str) -> dict[str, Any]:
    try:
        res = dispatch_gui(self, lambda: _open_checked(self, path))
    except Exception as exc:
        defaults = {}
        if isinstance(
            exc, (_DocumentOpenRejectedError, _DocumentOpenIdentityRejectedError)
        ):
            defaults = {
                "success": False,
                "error_code": exc.error_code,
            }
        return public_error(self, exc, **defaults)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


__all__ = ["list_documents", "open_document", "reload_document"]
