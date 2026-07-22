"""Document lock / lease operation wrappers."""

from __future__ import annotations

import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..lease_manager import LeaseClientManager, LeaseCredential
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
    selector: dict[str, Any] | None = None,
    agent_id: str = "",
    hash_policy: str = "sha256",
    lease_manager: LeaseClientManager | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        result = freecad.acquire_document_lock(
            doc_name=doc_name,
            file_path=file_path,
            session_id=session_id,
            task_description=task_description,
            client=client,
            selector=selector,
            agent_id=agent_id,
            hash_policy=hash_policy,
        )
        credential_data = result.get("credential") or {}
        document_data = result.get("document") or {}
        if result.get("success") and credential_data and lease_manager is not None:
            credential = LeaseCredential(
                lease_id=str(credential_data["lease_id"]),
                document_session_uuid=str(
                    credential_data["document_session_uuid"]
                ),
                generation=int(credential_data["generation"]),
                token=str(credential_data["token"]),
            )
            canonical_path = document_data.get("canonical_path")
            lease_manager.store(
                credential,
                canonical_paths=([canonical_path] if canonical_path else ()),
            )
            document_name = str(document_data.get("name") or doc_name or "")
            if document_name and document_sessions is not None:
                document_sessions[document_name] = credential.document_session_uuid
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
    try:
        freecad.set_active_lease_token(token)
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
