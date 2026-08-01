from __future__ import annotations

import logging
from typing import Any

from ...freecad_client import FreeCADConnection
from ...lease_manager import LeaseClientManager, LeaseCredential
from .store_grant_helpers import (
    _acknowledge_new_grant,
    _register_legacy_aliases,
    _resolve_redacted_credential,
)

logger = logging.getLogger("FreeCADMCPserver")


def _persist_credential(
    lease_manager: LeaseClientManager,
    credential: LeaseCredential,
    document_data: dict[str, Any],
) -> bool:
    try:
        canonical_path = document_data.get("canonical_path")
        lease_manager.store(
            credential,
            canonical_paths=([canonical_path] if canonical_path else ()),
        )
    except Exception:
        logger.exception(
            "local acquisition credential custody failed; escrow left unacknowledged"
        )
        return False
    return True


def _resolve_grant_credential(
    lease_manager: LeaseClientManager,
    credential_data: dict[str, Any],
) -> tuple[LeaseCredential, bool, bool]:
    token = str(credential_data.get("token") or "")
    if token in {"", "[REDACTED]"}:
        return _resolve_redacted_credential(lease_manager, credential_data), False, True
    return (
        LeaseCredential(
            lease_id=str(credential_data["lease_id"]),
            document_session_uuid=str(credential_data["document_session_uuid"]),
            generation=int(credential_data["generation"]),
            token=token,
        ),
        True,
        False,
    )


def _maybe_acknowledge_grant(
    freecad: FreeCADConnection,
    result: dict[str, Any],
    token: str,
) -> bool:
    try:
        return _acknowledge_new_grant(freecad, result, token)
    except Exception:
        logger.exception(
            "acquisition claim acknowledgement after custody failed; "
            "cleanup pending"
        )
        return True


def _store_lease_grant(
    result: dict[str, Any],
    *,
    lease_manager: LeaseClientManager | None,
    document_sessions: dict[str, str] | None,
    store_token: dict[str, str] | None,
    legacy_document_keys: dict[str, str] | None = None,
    fallback_document_name: str = "",
    freecad: FreeCADConnection | None = None,
) -> dict[str, Any]:
    """Custody a successful acquisition grant into the local lease manager."""

    outcome = {
        "credential_stored": False,
        "cleanup_pending": False,
        "stored_new_credential": False,
    }
    credential_data = result.get("credential") or {}
    document_data = result.get("document") or {}
    if not (result.get("success") and credential_data and lease_manager is not None):
        if result.get("success") and store_token is not None:
            _register_legacy_aliases(
                result=result,
                store_token=store_token,
                legacy_document_keys=legacy_document_keys,
                fallback_document_name=fallback_document_name,
                credential_data=credential_data,
            )
        return outcome

    token = str(credential_data.get("token") or "")
    credential, stored_new_credential, redacted_reused = _resolve_grant_credential(
        lease_manager,
        credential_data,
    )
    if redacted_reused:
        outcome["credential_stored"] = True
    if not _persist_credential(lease_manager, credential, document_data):
        return outcome

    outcome["credential_stored"] = True
    outcome["stored_new_credential"] = stored_new_credential
    document_name = str(document_data.get("name") or fallback_document_name or "")
    if document_name and document_sessions is not None:
        document_sessions[document_name] = credential.document_session_uuid
    if stored_new_credential and freecad is not None:
        outcome["cleanup_pending"] = _maybe_acknowledge_grant(freecad, result, token)
    if store_token is not None:
        _register_legacy_aliases(
            result=result,
            store_token=store_token,
            legacy_document_keys=legacy_document_keys,
            fallback_document_name=fallback_document_name,
            credential_data=credential_data,
        )
    return outcome
