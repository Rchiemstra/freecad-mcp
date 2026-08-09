"""Authentication/profile gate applied during RPC listener startup."""

from __future__ import annotations

import uuid
from typing import Any

from .abort_start import abort_rpc_start


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
    authentication_mode: str,
    profile_id: str,
    auth_secret_file: str,
) -> str | None:
    if authentication_mode != "enforce":
        return None
    if profile_id and profile_uuid_valid(profile_id) and auth_secret_file:
        return None
    abort_rpc_start(rpc_mod, close_listener=True)
    return (
        "RPC Server refused enforce mode because a UUID profile_instance_id "
        "and auth_secret_file are required"
    )
