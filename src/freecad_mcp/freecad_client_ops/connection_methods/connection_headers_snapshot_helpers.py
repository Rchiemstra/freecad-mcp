"""Helpers for authentication-only per-request header snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..constants import DIRECT_READ_METHODS

_V2_SELF_CONTAINED_METHODS = frozenset(
    {"invoke_v2", "invoke_v2_control", "handshake_v2"}
)


def is_v2_self_contained_method(method: str) -> bool:
    return method in _V2_SELF_CONTAINED_METHODS


def is_direct_read(method: str, args: tuple[Any, ...], session) -> bool:
    if session is None or not session.connected:
        return False
    if method in DIRECT_READ_METHODS:
        return True
    return (
        method == "execute_code"
        and len(args) > 1
        and isinstance(args[1], Mapping)
        and bool(args[1].get("read_only", False))
    )


def authenticated_request_headers(
    headers: tuple[tuple[str, str], ...],
    session,
    method: str,
) -> tuple[tuple[str, str], ...]:
    context = session.build_request_context(operation_name=method or "RPC request")
    return (
        *headers,
        ("X-MCP-Session-Token", context.session_token),
        ("X-MCP-Request-Id", context.request_id),
        ("X-MCP-Lease-Credentials", "[]"),
    )


def direct_read_request_headers(
    headers: tuple[tuple[str, str], ...],
    session,
    method: str,
) -> tuple[tuple[str, str], ...]:
    """Compatibility name for the authentication-only header builder."""

    return authenticated_request_headers(headers, session, method)


def legacy_lease_token_headers(
    headers: tuple[tuple[str, str], ...],
    conn,
) -> None:
    """The retired per-document token header is never emitted."""

    del headers, conn


def document_names_from_args(method: str, args: tuple[Any, ...]) -> list[str]:
    """Retain the former helper signature without participating in routing."""

    del method, args
    return []


def selector_argument(method: str, args: tuple[Any, ...]) -> None:
    """Retain the former helper signature without participating in routing."""

    del method, args


def session_ids_from_selector(
    selector: Mapping[str, Any],
    manager,
    document_names: list[str],
    session_ids: list[str],
) -> None:
    """Retain the former helper signature without resolving document aliases."""

    del selector, manager, document_names, session_ids


def resolve_session_ids(
    resolver,
    document_names: list[str],
    session_ids: list[str],
) -> None:
    """Retain the former helper signature without resolving document aliases."""

    del resolver, document_names, session_ids


def manager_request_headers(
    headers: tuple[tuple[str, str], ...],
    manager,
    *,
    session_ids: list[str],
    method: str,
) -> tuple[tuple[str, str], ...]:
    """Compatibility name for authentication-only headers."""

    del session_ids
    return authenticated_request_headers(headers, manager, method)
