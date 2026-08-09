"""Authenticated RPC v2 session setup during listener startup."""

from __future__ import annotations

import logging
from typing import Any

from .abort_start import abort_rpc_start

logger = logging.getLogger("FreeCADMCP.rpc_server")


def initialize_rpc_v2_session(
    rpc_mod: Any,
    *,
    profile_id: str,
    auth_secret_file: str,
    authentication_mode: str,
    actual_host: str,
    actual_port: int,
) -> str:
    rpc_mod.rpc_session_manager = None
    rpc_mod.rpc_runtime_manifest = None
    if not profile_id or not auth_secret_file:
        return ""
    try:
        secret = rpc_mod.load_profile_secret(auth_secret_file)
        version_parts = list(rpc_mod._freecad_version_parts())
        freecad_version_text = ".".join(version_parts[:3]) or "unknown"
        freecad_revision = (
            version_parts[3]
            if len(version_parts) > 3 and version_parts[3]
            else "unknown"
        )
        rpc_mod.rpc_runtime_manifest = rpc_mod.make_runtime_manifest(
            profile_id=profile_id,
            addon_runtime_id=rpc_mod.rpc_server_runtime_id,
            freecad_pid=rpc_mod.os.getpid(),
            freecad_process_started_at=rpc_mod.rpc_server_started_at or None,
            boot_id=rpc_mod._boot_identity(),
            rpc_host=str(actual_host),
            rpc_port=int(actual_port),
            freecad_version=freecad_version_text,
            freecad_revision=freecad_revision,
            addon_version=rpc_mod.addon_version,
            addon_build_id=rpc_mod.addon_build_id,
            profile_path_fingerprint=rpc_mod._profile_fingerprint(),
        )
        rpc_mod.rpc_session_manager = rpc_mod.SessionManager(
            manifest=rpc_mod.rpc_runtime_manifest, secret=secret
        )
        return ""
    except Exception as exc:
        logger.error("Could not initialize authenticated RPC v2: %s", exc)
        if authentication_mode == "enforce":
            abort_rpc_start(rpc_mod, close_listener=True)
            return "RPC Server could not initialize authenticated RPC protocol"
        return (
            " WARNING: authenticated RPC protocol v2 is unavailable; "
            "check profile_instance_id and auth_secret_file "
            f"({rpc_mod._redact_rpc_diagnostic(exc)})."
        )
