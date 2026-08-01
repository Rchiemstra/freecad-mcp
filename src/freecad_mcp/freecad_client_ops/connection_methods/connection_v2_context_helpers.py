"""Helpers for resolving authenticated RPC v2 request context."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ...lease_manager import LeaseClientManager, LeaseNotFoundError


def resolve_document_name_sessions(
    resolver,
    document_names: Iterable[str],
    add_session,
) -> None:
    for raw_name in document_names:
        name = str(raw_name or "")
        if not name:
            continue
        session_uuid = resolver(name) if resolver is not None else None
        if not session_uuid:
            raise LeaseNotFoundError(
                f"no active lease credential is mapped to document {name!r}"
            )
        add_session(session_uuid)


def resolve_selector_session(
    manager: LeaseClientManager,
    resolver,
    raw_selector: Mapping[str, Any],
    add_session,
) -> None:
    selector = dict(raw_selector or {})
    selected_uuid = str(selector.get("document_session_uuid") or "")
    selected_name = str(selector.get("document_name") or "")
    selected_path = str(selector.get("canonical_path") or "")

    name_uuid = resolver(selected_name) if selected_name and resolver is not None else None
    if selected_name and not name_uuid and not selected_uuid and not selected_path:
        raise LeaseNotFoundError(
            f"no active lease credential is mapped to document {selected_name!r}"
        )
    if selected_uuid and name_uuid and selected_uuid != name_uuid:
        raise LeaseNotFoundError(
            "selector document name and session UUID identify different leases"
        )

    credential = None
    if selected_uuid or selected_path:
        credential = manager.get(
            document_session_uuid=selected_uuid or None,
            canonical_path=selected_path or None,
        )
        if credential is None:
            raise LeaseNotFoundError(
                "selector does not identify an active lease credential"
            )
    elif name_uuid:
        credential = manager.get(document_session_uuid=name_uuid)
    if credential is not None:
        add_session(credential.document_session_uuid)
