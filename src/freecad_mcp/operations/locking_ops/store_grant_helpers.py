from __future__ import annotations

import os
from typing import Any

from ...freecad_client import FreeCADConnection
from ...lease_manager import LeaseClientManager, LeaseCredential
from .legacy_keys import _legacy_alias


def _resolve_redacted_credential(
    lease_manager: LeaseClientManager,
    credential_data: dict[str, Any],
) -> LeaseCredential | None:
    lease_id = str(credential_data["lease_id"])
    document_session_uuid = str(credential_data["document_session_uuid"])
    generation = int(credential_data["generation"])
    current = lease_manager.get(document_session_uuid=document_session_uuid)
    if (
        current is not None
        and current.lease_id == lease_id
        and current.generation == generation
    ):
        return current
    raise ValueError("redacted acquisition replay has no matching local credential")


def _register_legacy_aliases(
    *,
    result: dict[str, Any],
    store_token: dict[str, str],
    legacy_document_keys: dict[str, str] | None,
    fallback_document_name: str,
    credential_data: dict[str, Any],
) -> None:
    lease = result.get("lease") or {}
    token = result.get("token") or lease.get("token")
    doc_key = lease.get("doc_key")
    if not token or not doc_key:
        return
    store_token[doc_key] = token
    if legacy_document_keys is None or credential_data:
        return
    aliases = (
        _legacy_alias("name", lease.get("doc_name") or fallback_document_name),
        _legacy_alias("session", lease.get("document_session_uuid")),
        _legacy_alias("path", doc_key if os.path.isabs(doc_key) else ""),
    )
    for alias in aliases:
        if alias:
            legacy_document_keys[alias] = str(doc_key)


def _acknowledge_new_grant(
    freecad: FreeCADConnection,
    result: dict[str, Any],
    token: str,
) -> bool:
    if not result.get("request_id") or token in {"", "[REDACTED]"}:
        return False
    freecad.acknowledge_acquisition_claim(str(result["request_id"]))
    return True
