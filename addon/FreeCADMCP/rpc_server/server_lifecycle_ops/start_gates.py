"""Lease-mode and profile gates applied during RPC listener startup."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import FreeCAD

from .abort_start import abort_rpc_start

logger = logging.getLogger("FreeCADMCP.rpc_server")


def profile_uuid_valid(profile_id: str) -> bool:
    if not profile_id:
        return False
    try:
        uuid.UUID(profile_id)
        return True
    except (ValueError, AttributeError):
        return False


def refuse_enforce_without_profile(
    rpc_mod: Any,
    *,
    lease_mode: str,
    profile_id: str,
    auth_secret_file: str,
) -> str | None:
    if lease_mode != "enforce":
        return None
    if profile_id and profile_uuid_valid(profile_id) and auth_secret_file:
        return None
    abort_rpc_start(rpc_mod, close_listener=True)
    return (
        "RPC Server refused enforce mode because a UUID profile_instance_id "
        "and auth_secret_file are required"
    )


def refuse_off_mode_with_active_records(rpc_mod: Any, lease_mode: str) -> str | None:
    if lease_mode != "off":
        return None
    active_records = (
        rpc_mod.document_lease_service.list_records()
        if rpc_mod.document_lease_service is not None
        else []
    )
    if not active_records:
        return None
    abort_rpc_start(rpc_mod, close_listener=True)
    return (
        "RPC Server refused document_lease_mode=off while active v2 "
        "lease or recovery records exist"
    )


def register_live_documents(rpc_mod: Any, lease_mode: str) -> None:
    if lease_mode == "off":
        return
    try:
        for document in FreeCAD.listDocuments().values():
            rpc_mod._ensure_v2_document(document)
    except Exception as exc:
        logger.warning("Could not register all live document identities: %s", exc)
