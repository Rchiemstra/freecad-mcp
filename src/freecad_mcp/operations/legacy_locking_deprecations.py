"""Frozen root-import adapters for retired MCP document-lock operations.

These names preserve the Phase 17 ``freecad_mcp.operations`` import contract.
They deliberately do not import the historic ``operations.locking`` module or
its implementation package: native FreeCAD collaboration owns document
authority after the Phase 18 cutover.
"""

from __future__ import annotations

from typing import Any


def _removed() -> dict[str, object]:
    """Return a fresh copy of the frozen compatibility result."""

    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": "Document authority is owned by native FreeCAD collaboration.",
    }


def acquire_document_lock_operation(
    freecad: object,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    task_description: str = "",
    client: str = "",
    selector: dict[str, Any] | None = None,
    agent_id: str = "",
    hash_policy: str = "sha256",
    lease_manager: object | None = None,
    document_sessions: dict[str, str] | None = None,
) -> dict[str, object]:
    del (
        freecad,
        doc_name,
        file_path,
        session_id,
        task_description,
        client,
        selector,
        agent_id,
        hash_policy,
        lease_manager,
        document_sessions,
    )
    return _removed()


def adopt_dirty_document_operation(
    freecad: object,
    *,
    selector: dict[str, Any],
    task_description: str = "",
    client: str = "",
    agent_id: str = "",
    hash_policy: str = "sha256",
    lease_manager: object | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> dict[str, object]:
    del (
        freecad,
        selector,
        task_description,
        client,
        agent_id,
        hash_policy,
        lease_manager,
        document_sessions,
        store_token,
    )
    return _removed()


def claim_acquisition_result_operation(
    freecad: object,
    *,
    request_id: str,
    lease_manager: object | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> dict[str, object]:
    del freecad, request_id, lease_manager, document_sessions, store_token
    return _removed()


def get_document_lock_operation(
    freecad: object,
    *,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    selector: dict[str, Any] | None = None,
) -> dict[str, object]:
    del freecad, doc_name, file_path, session_id, selector
    return _removed()


def list_document_locks_operation(freecad: object) -> dict[str, object]:
    del freecad
    return _removed()


def heartbeat_document_lock_operation(
    freecad: object,
    *,
    doc_key: str,
    token: str,
    current_operation: str = "",
    state: str = "",
    document_dirty: bool | None = None,
) -> dict[str, object]:
    del freecad, doc_key, token, current_operation, state, document_dirty
    return _removed()


def update_document_lock_operation(
    freecad: object,
    *,
    selector: dict[str, Any],
    task_description: str = "",
    progress_detail: str = "",
) -> dict[str, object]:
    del freecad, selector, task_description, progress_detail
    return _removed()


def release_document_lock_operation(
    freecad: object,
    *,
    doc_key: str,
    token: str,
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
    lease_manager: object | None = None,
    document_sessions: dict[str, str] | None = None,
    store_token: dict[str, str] | None = None,
) -> dict[str, object]:
    del (
        freecad,
        doc_key,
        token,
        selector,
        disposition,
        lease_manager,
        document_sessions,
        store_token,
    )
    return _removed()


def force_release_stale_lock_operation(
    freecad: object,
    *,
    doc_key: str,
) -> dict[str, object]:
    del freecad, doc_key
    return _removed()


def legacy_selector_doc_key(
    selector: dict[str, Any],
    legacy_document_keys: dict[str, str],
) -> dict[str, object]:
    del selector, legacy_document_keys
    return _removed()


def forget_legacy_document_key(
    doc_key: str,
    legacy_document_keys: dict[str, str] | None,
) -> dict[str, object]:
    del doc_key, legacy_document_keys
    return _removed()


__all__ = [
    "acquire_document_lock_operation",
    "adopt_dirty_document_operation",
    "claim_acquisition_result_operation",
    "force_release_stale_lock_operation",
    "forget_legacy_document_key",
    "get_document_lock_operation",
    "heartbeat_document_lock_operation",
    "legacy_selector_doc_key",
    "list_document_locks_operation",
    "release_document_lock_operation",
    "update_document_lock_operation",
]
