"""Helpers for building per-request RPC header snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..constants import DIRECT_READ_METHODS

_V2_SELF_CONTAINED_METHODS = frozenset(
    {"invoke_v2", "invoke_v2_control", "handshake_v2"}
)
_SELECTOR_METHODS = frozenset(
    {
        "update_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }
)


def is_v2_self_contained_method(method: str) -> bool:
    return method in _V2_SELF_CONTAINED_METHODS


def is_direct_read(method: str, args: tuple[Any, ...], manager) -> bool:
    if manager is None or not manager.connected:
        return False
    if method in DIRECT_READ_METHODS:
        return True
    return (
        method == "execute_code"
        and len(args) > 1
        and isinstance(args[1], Mapping)
        and bool(args[1].get("read_only", False))
    )


def direct_read_request_headers(
    headers: tuple[tuple[str, str], ...],
    manager,
    method: str,
) -> tuple[tuple[str, str], ...]:
    context = manager.build_request_context(operation_name=method or "RPC read")
    return (
        *headers,
        ("X-MCP-Session-Token", context.session_token),
        ("X-MCP-Request-Id", context.request_id),
        ("X-MCP-Lease-Credentials", "[]"),
    )


def legacy_lease_token_headers(
    headers: tuple[tuple[str, str], ...],
    conn,
) -> tuple[tuple[str, str], ...] | None:
    token_var = getattr(conn, "_legacy_lease_token", None)
    token = token_var.get() if token_var is not None else None
    if not token:
        return None
    return (*headers, ("X-MCP-Lease-Token", str(token)))


def document_names_from_args(method: str, args: tuple[Any, ...]) -> list[str]:
    document_names: list[str] = []
    if method == "execute_code" and len(args) > 1 and isinstance(args[1], Mapping):
        options = args[1]
        primary = options.get("document")
        if isinstance(primary, str) and primary:
            document_names.append(primary)
        for name in options.get("affected_documents") or ():
            if isinstance(name, str) and name and name not in document_names:
                document_names.append(name)
    elif args and isinstance(args[0], str):
        document_names.append(args[0])
    return document_names


def selector_argument(method: str, args: tuple[Any, ...]) -> Mapping[str, Any] | None:
    if method == "release_document_lock" and len(args) > 2 and isinstance(args[2], Mapping):
        return args[2]
    if args and isinstance(args[0], Mapping) and method in _SELECTOR_METHODS:
        return args[0]
    return None


def session_ids_from_selector(
    selector: Mapping[str, Any],
    manager,
    document_names: list[str],
    session_ids: list[str],
) -> None:
    selected_session = selector.get("document_session_uuid")
    if isinstance(selected_session, str) and selected_session:
        session_ids.append(selected_session)
    selected_name = selector.get("document_name")
    if isinstance(selected_name, str) and selected_name:
        document_names.append(selected_name)
    selected_path = selector.get("canonical_path")
    if isinstance(selected_path, str) and selected_path:
        selected = manager.get(canonical_path=selected_path)
        if selected is not None and selected.document_session_uuid not in session_ids:
            session_ids.append(selected.document_session_uuid)


def resolve_session_ids(
    resolver,
    document_names: list[str],
    session_ids: list[str],
) -> None:
    if resolver is None:
        return
    for name in document_names:
        session_uuid = resolver(name)
        if session_uuid and session_uuid not in session_ids:
            session_ids.append(session_uuid)


def manager_request_headers(
    headers: tuple[tuple[str, str], ...],
    manager,
    *,
    session_ids: list[str],
    method: str,
) -> tuple[tuple[str, str], ...]:
    try:
        context = manager.build_request_context(
            document_session_uuids=session_ids,
            operation_name=method or "RPC request",
        )
    except Exception:
        context = manager.build_request_context(operation_name=method or "RPC request")
    credential_payload = [item.to_wire() for item in context.lease_credentials]
    routed = (
        *headers,
        ("X-MCP-Session-Token", context.session_token),
        ("X-MCP-Request-Id", context.request_id),
        (
            "X-MCP-Lease-Credentials",
            json.dumps(
                credential_payload,
                ensure_ascii=True,
                separators=(",", ":"),
            ),
        ),
    )
    if len(credential_payload) != 1:
        return routed
    credential = credential_payload[0]
    return (
        *routed,
        ("X-MCP-Lease-Id", credential["lease_id"]),
        ("X-MCP-Lease-Generation", str(credential["generation"])),
        ("X-MCP-Document-Session-Id", credential["document_session_uuid"]),
        ("X-MCP-Lease-Token", credential["token"]),
    )
