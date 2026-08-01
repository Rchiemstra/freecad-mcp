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
    lease_mode: str,
    actual_host: str,
    actual_port: int,
) -> str:
    rpc_mod.rpc_session_manager = None
    rpc_mod.rpc_runtime_manifest = None
    if not profile_id or not auth_secret_file:
        return ""
    try:
        secret = rpc_mod.load_profile_secret(auth_secret_file)
        lease_runtime = rpc_mod._require_authenticated_lease_runtime(profile_id)
        version_parts = list(rpc_mod._freecad_version_parts())
        freecad_version_text = ".".join(version_parts[:3]) or "unknown"
        freecad_revision = (
            version_parts[3]
            if len(version_parts) > 3 and version_parts[3]
            else "unknown"
        )
        rpc_mod.rpc_runtime_manifest = rpc_mod.make_runtime_manifest(
            profile_id=profile_id,
            addon_runtime_id=lease_runtime.addon_runtime_id,
            freecad_pid=lease_runtime.freecad_pid,
            freecad_process_started_at=(lease_runtime.freecad_process_started_at),
            boot_id=lease_runtime.boot_id,
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
        rpc_mod.rpc_request_replay_cache.set_owner_lease_predicate(
            rpc_mod.document_lease_service.has_unresolved_owner
        )
        return ""
    except Exception as exc:
        logger.error("Could not initialize authenticated RPC v2: %s", exc)
        if lease_mode == "enforce":
            abort_rpc_start(rpc_mod, close_listener=True)
            return "RPC Server could not initialize authenticated lease protocol"
        return (
            " WARNING: authenticated RPC protocol v2 is unavailable; "
            "check profile_instance_id, auth_secret_file, and trusted "
            f"boot/process identity ({rpc_mod._redact_rpc_diagnostic(exc)})."
        )
