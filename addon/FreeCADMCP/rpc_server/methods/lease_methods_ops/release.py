"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from contextlib import suppress
from typing import Any

from .lifecycle_dependencies import LifecycleCollaborators
from .release_gui import release_document_gui


def release_document_lock(
    self,
    doc_key: str = "",
    token: str = "",
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
) -> dict[str, Any]:
    collaborators: LifecycleCollaborators = self._lifecycle_collaborators
    try:
        dl = collaborators.import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false",
        }
    if collaborators.document_lease_service is not None and selector is not None:
        captured_identity = dict(dl.get_request_identity())
        inflight = self._current_inflight()
        self._request_checkpoint("release_start")

        def task():
            try:
                return release_document_gui(
                    self,
                    selector=selector,
                    disposition=disposition,
                    captured_identity=captured_identity,
                    inflight=inflight,
                    collaborators=collaborators,
                )
            except Exception as exc:
                return collaborators.lease_service_error(
                    exc, request_id=captured_identity.get("request_id")
                )

        return self._dispatch_gui(task, timeout=self.EXECUTE_TIMEOUT)
    result = dl.release_lease(doc_key, token)
    if result.get("success"):
        with suppress(Exception):
            collaborators.refresh_lock_indicator()
    return result


def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
    """Reject remote force release; recovery is a confirmed local GUI action.

    The method remains as a compatibility tombstone so an older client
    receives an explicit safe failure instead of an XML-RPC unknown-method
    fault.  In particular it must not become usable merely by switching a
    profile to observe/off mode.
    """
    del doc_key
    collaborators: LifecycleCollaborators = self._lifecycle_collaborators
    return collaborators.deprecated_force_release_result()
