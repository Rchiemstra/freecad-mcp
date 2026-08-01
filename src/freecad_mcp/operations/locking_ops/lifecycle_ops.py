from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...lease_manager import LeaseClientManager
from ...responses import ToolResponse, tool_fail
from .response_helpers import _lock_response

logger = logging.getLogger("FreeCADMCPserver")

def get_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        return _lock_response(
            freecad.get_document_lock(
                doc_name=doc_name,
                file_path=file_path,
                session_id=session_id,
                selector=selector,
            )
        )
    except Exception as exc:
        return tool_fail(f"get_document_lock failed: {exc}")

def list_document_locks_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        return _lock_response(freecad.list_document_locks())
    except Exception as exc:
        return tool_fail(f"list_document_locks failed: {exc}")

def heartbeat_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
) -> ToolResponse:
    try:
        freecad.set_active_lease_token(token)
        return _lock_response(
            freecad.heartbeat_document_lock(
                doc_key,
                token,
                current_operation=current_operation,
                state=state,
                document_dirty=document_dirty,
            )
        )
    except Exception as exc:
        return tool_fail(f"heartbeat_document_lock failed: {exc}")

def update_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    selector: dict[str, Any],
    task_description: str = "",
    progress_detail: str = "",
) -> ToolResponse:
    try:
        return _lock_response(
            freecad.update_document_lock(
                selector,
                task_description=task_description,
                progress_detail=progress_detail,
            )
        )
    except Exception as exc:
        return tool_fail(f"update_document_lock failed: {exc}")

def release_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
    token: str,
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    freecad.set_active_lease_token(token)
    try:
        result = freecad.release_document_lock(
            doc_key,
            token,
            selector=selector,
            disposition=disposition,
        )
        if result.get("success") and selector and lease_manager is not None:
            session_uuid = str(selector.get("document_session_uuid") or "")
            if session_uuid:
                lease_manager.revoke(session_uuid, reason="clean lease release")
                if document_sessions is not None:
                    for name, value in list(document_sessions.items()):
                        if value == session_uuid:
                            document_sessions.pop(name, None)
        if result.get("success") and store_token is not None:
            store_token.pop(doc_key, None)
        return _lock_response(result)
    except Exception as exc:
        return tool_fail(f"release_document_lock failed: {exc}")
    finally:
        freecad.set_active_lease_token(None)

def force_release_stale_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
) -> ToolResponse:
    try:
        return _lock_response(freecad.force_release_stale_lock(doc_key))
    except Exception as exc:
        return tool_fail(f"force_release_stale_lock failed: {exc}")
