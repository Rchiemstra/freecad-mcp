"""Document lock / lease operation wrappers."""

from __future__ import annotations

import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, json_response, tool_fail

logger = logging.getLogger("FreeCADMCPserver")


def _lock_response(result: dict[str, Any]) -> ToolResponse:
    if not isinstance(result, dict):
        return tool_fail(f"Unexpected lock response: {result!r}")
    if result.get("success"):
        return json_response(result)
    code = result.get("error_code") or "lock_error"
    message = result.get("error") or code
    return tool_fail(f"[{code}] {message}", structured=result)


def acquire_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    task_description: str = "",
    client: str = "",
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        result = freecad.acquire_document_lock(
            doc_name=doc_name,
            file_path=file_path,
            session_id=session_id,
            task_description=task_description,
            client=client,
        )
        if result.get("success") and store_token is not None:
            lease = result.get("lease") or {}
            token = result.get("token") or lease.get("token")
            doc_key = lease.get("doc_key")
            if token and doc_key:
                store_token[doc_key] = token
            # Do not pin a single active token on the transport: mutations
            # authenticate by instance_id; token is validated only when sent
            # (heartbeat / release). Pinning the last-acquired token would
            # break multi-document sessions.
        return _lock_response(result)
    except Exception as exc:
        logger.error("acquire_document_lock failed: %s", exc)
        return tool_fail(f"acquire_document_lock failed: {exc}")


def get_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
) -> ToolResponse:
    try:
        return _lock_response(
            freecad.get_document_lock(
                doc_name=doc_name, file_path=file_path, session_id=session_id
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


def release_document_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
    token: str,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        freecad.set_active_lease_token(token)
        result = freecad.release_document_lock(doc_key, token)
        if result.get("success") and store_token is not None:
            store_token.pop(doc_key, None)
        freecad.set_active_lease_token(None)
        return _lock_response(result)
    except Exception as exc:
        return tool_fail(f"release_document_lock failed: {exc}")


def force_release_stale_lock_operation(
    freecad: FreeCADConnection,
    *,
    doc_key: str,
) -> ToolResponse:
    try:
        return _lock_response(freecad.force_release_stale_lock(doc_key))
    except Exception as exc:
        return tool_fail(f"force_release_stale_lock failed: {exc}")
