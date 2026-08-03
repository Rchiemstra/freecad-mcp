"""Helpers for closing FreeCAD RPC transport lanes."""

from __future__ import annotations


def mark_connection_disconnected(conn) -> bool:
    with conn._identity_lock:
        if conn._disconnected:
            return False
        conn._disconnected = True
        manager = conn._lease_manager
        conn._session_refresher = None
    if manager is not None:
        manager.mark_disconnected("FreeCAD RPC connection disconnected")
    token_var = getattr(conn, "_legacy_lease_token", None)
    if token_var is not None:
        token_var.set(None)
    return True


def close_transport_lane(
    lane,
    seen: set[int],
    first_error: BaseException | None,
) -> BaseException | None:
    if lane is None or id(lane) in seen:
        return first_error
    seen.add(id(lane))
    close = getattr(lane, "close", None)
    if callable(close):
        try:
            close()
        except Exception as exc:
            if first_error is None:
                first_error = exc
        return first_error
    return first_error
