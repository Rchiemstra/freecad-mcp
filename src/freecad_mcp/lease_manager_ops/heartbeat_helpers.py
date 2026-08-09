"""Heartbeat batch parsing helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .stale_recovery_constants import _upper_state


def heartbeat_item_lease_state(item: Mapping[str, Any]) -> str:
    """Return the reported lease state from one heartbeat batch item."""

    state = _upper_state(item.get("state"))
    if state:
        return state
    lease = item.get("lease")
    if isinstance(lease, Mapping):
        state = _upper_state(lease.get("state"))
        if state:
            return state
    details = item.get("details")
    if isinstance(details, Mapping):
        return _upper_state(details.get("state"))
    return ""


def is_timeout_stale_heartbeat_item(item: Mapping[str, Any]) -> bool:
    """True when a heartbeat item reports a timeout-induced STALE lease."""

    if heartbeat_item_lease_state(item) == "STALE":
        return True
    error_code = _upper_state(item.get("error_code") or item.get("code"))
    if error_code != "LEASE_STATE_FORBIDS_OPERATION":
        return False
    return heartbeat_item_lease_state(item) == "STALE"


def _heartbeat_lease_items(response: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return normalized lease items from one heartbeat batch response."""

    raw_results: Any = response.get("leases", response.get("results", ()))
    if isinstance(raw_results, Mapping):
        results: Sequence[Any] = tuple(raw_results.values())
    elif isinstance(raw_results, Sequence) and not isinstance(
        raw_results, (str, bytes)
    ):
        results = raw_results
    else:
        results = ()
    items: list[Mapping[str, Any]] = []
    for item in results:
        if isinstance(item, Mapping):
            items.append(item)
    return tuple(items)


def heartbeat_item_confirms_active_lease(item: Mapping[str, Any]) -> bool:
    """True when a heartbeat item proves the lease is still active (not STALE)."""

    if is_timeout_stale_heartbeat_item(item):
        return False
    if item.get("success") is False:
        return False
    state = heartbeat_item_lease_state(item)
    if not state:
        return item.get("success") is True
    if state == "STALE":
        return False
    return state.startswith("LOCKED_") or state == "ACQUIRING"


def extract_stale_sessions_from_heartbeat(
    response: Mapping[str, Any],
) -> tuple[str, ...]:
    """Collect held document session UUIDs reported as STALE by heartbeat."""

    stale: list[str] = []
    for item in _heartbeat_lease_items(response):
        if not is_timeout_stale_heartbeat_item(item):
            continue
        session_uuid = str(
            item.get("document_session_uuid") or item.get("session_uuid") or ""
        )
        if session_uuid:
            stale.append(session_uuid)
    return tuple(stale)


def extract_active_sessions_from_heartbeat(
    response: Mapping[str, Any],
) -> tuple[str, ...]:
    """Collect session UUIDs whose heartbeat item proves an active lease."""

    active: list[str] = []
    for item in _heartbeat_lease_items(response):
        if not heartbeat_item_confirms_active_lease(item):
            continue
        session_uuid = str(
            item.get("document_session_uuid") or item.get("session_uuid") or ""
        )
        if session_uuid:
            active.append(session_uuid)
    return tuple(active)
