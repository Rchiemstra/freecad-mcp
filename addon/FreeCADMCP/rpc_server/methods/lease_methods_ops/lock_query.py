"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

import hashlib
from contextlib import suppress
from typing import Any

from .lifecycle_dependencies import LifecycleCollaborators
from .lock_query_helpers import lease_service_get_lock, list_v1_locks, list_v2_locks


def get_document_lock(
    self,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
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
    if not (doc_name or file_path or session_id or selector):
        return {
            "success": False,
            "error_code": "document_identity_required",
            "error": "Provide doc_name, file_path, or session_id",
        }
    if collaborators.document_lease_service is not None:
        try:
            return lease_service_get_lock(
                doc_name=doc_name,
                file_path=file_path,
                session_id=session_id,
                selector=selector,
                dl=dl,
                collaborators=collaborators,
            )
        except Exception as exc:
            return collaborators.lease_service_error(exc)
    try:
        key = dl.resolve_doc_key(
            doc_name=doc_name or None,
            file_path=file_path or None,
            session_id=session_id or None,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    lease = dl.get_lease(key)
    if lease is None:
        return {"success": True, "locked": False, "doc_key": key, "lease": None}
    return {
        "success": True,
        "locked": True,
        "doc_key": key,
        "lease": lease.to_dict(),
    }


def list_document_locks(self) -> dict[str, Any]:
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

    def task():
        if collaborators.document_lease_service is not None:
            return list_v2_locks(dl, collaborators=collaborators)
        return list_v1_locks(dl, collaborators=collaborators)

    return self._dispatch_gui(task)


def heartbeat_document_lock(
    self,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
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
    safe_current_operation = collaborators.redact_rpc_diagnostic(current_operation)
    if token:
        safe_current_operation = safe_current_operation.replace(
            str(token), "<redacted>"
        ).replace(
            "sha256:" + hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
            "<redacted>",
        )
    result = dl.heartbeat_lease(
        doc_key,
        token,
        current_operation=safe_current_operation or None,
        state=state or None,
        document_dirty=document_dirty,
    )
    if result.get("success"):
        with suppress(Exception):
            collaborators.refresh_lock_indicator()
    return result


def update_document_lock(
    self,
    selector,
    task_description="",
    progress_detail="",
):
    """Update bounded diagnostics only; state and dirty flags are authoritative."""
    collaborators: LifecycleCollaborators = self._lifecycle_collaborators
    if collaborators.document_lease_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Document lease v2 is not initialized",
        }
    try:
        credential, _document_identity, _document = collaborators.credential_for_selector(
            selector
        )
        request_identity = collaborators.import_document_lock().get_request_identity()
        operation = collaborators.redact_rpc_diagnostic(
            progress_detail, identity=request_identity
        )[:512]
        task = collaborators.redact_rpc_diagnostic(task_description, identity=request_identity)[
            :1024
        ]
        status = collaborators.document_lease_service.update_metadata(
            credential,
            task_summary=task if task_description else None,
            current_operation=operation if progress_detail else None,
        )
        return {"success": True, "lease": status}
    except Exception as exc:
        return collaborators.lease_service_error(exc)
