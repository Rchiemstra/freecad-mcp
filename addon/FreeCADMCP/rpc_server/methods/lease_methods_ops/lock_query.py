"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

import hashlib
from typing import Any

from ._common import _rpc_mod
from .lock_query_helpers import lease_service_get_lock, list_v1_locks, list_v2_locks


def get_document_lock(
    self,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        dl = _rpc_mod()._import_document_lock()
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
    if _rpc_mod().document_lease_service is not None:
        try:
            return lease_service_get_lock(
                doc_name=doc_name,
                file_path=file_path,
                session_id=session_id,
                selector=selector,
                dl=dl,
            )
        except Exception as exc:
            return _rpc_mod()._lease_service_error(exc)
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
    try:
        dl = _rpc_mod()._import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false",
        }

    def task():
        if _rpc_mod().document_lease_service is not None:
            return list_v2_locks(dl)
        return list_v1_locks(dl)

    return self._dispatch_gui(task)


def heartbeat_document_lock(
    self,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
) -> dict[str, Any]:
    try:
        dl = _rpc_mod()._import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false",
        }
    safe_current_operation = _rpc_mod()._redact_rpc_diagnostic(current_operation)
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
        try:
            from lock_indicator import refresh_lock_indicator

            refresh_lock_indicator()
        except Exception:
            pass
    return result


def update_document_lock(
    self,
    selector,
    task_description="",
    progress_detail="",
):
    """Update bounded diagnostics only; state and dirty flags are authoritative."""
    if _rpc_mod().document_lease_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Document lease v2 is not initialized",
        }
    try:
        credential, _document_identity, _document = _rpc_mod()._credential_for_selector(
            selector
        )
        request_identity = _rpc_mod()._import_document_lock().get_request_identity()
        operation = _rpc_mod()._redact_rpc_diagnostic(
            progress_detail, identity=request_identity
        )[:512]
        task = _rpc_mod()._redact_rpc_diagnostic(task_description, identity=request_identity)[
            :1024
        ]
        status = _rpc_mod().document_lease_service.update_metadata(
            credential,
            task_summary=task if task_description else None,
            current_operation=operation if progress_detail else None,
        )
        return {"success": True, "lease": status}
    except Exception as exc:
        return _rpc_mod()._lease_service_error(exc)
