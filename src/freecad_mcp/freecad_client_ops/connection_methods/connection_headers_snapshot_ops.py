"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from typing import Any

from .connection_headers_snapshot_helpers import (
    direct_read_request_headers,
    document_names_from_args,
    is_direct_read,
    is_v2_self_contained_method,
    legacy_lease_token_headers,
    manager_request_headers,
    resolve_session_ids,
    selector_argument,
    session_ids_from_selector,
)

logger = logging.getLogger("FreeCADMCPserver")


def _request_headers_snapshot(
    conn, method: str = "", args: tuple[Any, ...] = ()
) -> tuple[tuple[str, str], ...]:
    with conn._identity_lock:
        headers = conn._base_headers
        manager = conn._lease_manager
        resolver = conn._document_session_resolver
    # v2 carries its complete immutable authentication context in the
    # envelope.  Do not add a second, independently generated request id
    # or any lease credential headers to that call.
    if is_v2_self_contained_method(method):
        return headers
    if is_direct_read(method, args, manager):
        return direct_read_request_headers(headers, manager, method)
    legacy_headers = legacy_lease_token_headers(headers, conn)
    if legacy_headers is not None:
        return legacy_headers
    if manager is None or not manager.connected:
        return headers
    document_names = document_names_from_args(method, args)
    session_ids: list[str] = []
    selected = selector_argument(method, args)
    if selected is not None:
        session_ids_from_selector(selected, manager, document_names, session_ids)
    resolve_session_ids(resolver, document_names, session_ids)
    return manager_request_headers(
        headers,
        manager,
        session_ids=session_ids,
        method=method,
    )
