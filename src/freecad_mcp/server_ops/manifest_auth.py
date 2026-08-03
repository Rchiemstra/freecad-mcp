"""Manifest Auth (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from typing import Any

from .._shared.protocol.handshake_request import build_handshake_request_from_manifest
from .._shared.protocol.handshake_response import (
    verify_handshake_response_from_manifest,
)
from .._shared.protocol.manifest import load_instance_manifest, make_mcp_runtime_identity
from .._shared.protocol.profile_secret import load_profile_secret
from .._shared.protocol.protocol_error import ProtocolError as RpcAuthError
from ..build_info import as_dict as build_info_dict
from ..build_info import build_id, protocol_version
from ..freecad_client import FreeCADConnection
from ..outcomes import OutcomeStatus
from . import surfaces
from .compatibility import compatibility_for_manifest
from .paths import path_identity
from .session import session_needs_refresh


def manifest_for_authentication() -> Any:
    """Reload runtime facts from the launcher's fixed manifest path.

    Runtime identity fields are expected to change after a launcher-authorized
    FreeCAD restart.  Profile identity/path, RPC endpoint, authentication-file
    path, schema, and creation identity are immutable for this MCP process.
    """

    baseline = surfaces.state.instance_manifest
    if baseline is None:
        return None
    configured_path = surfaces.state.instance_manifest_path
    if not configured_path:
        # Compatibility for embedded/unit callers which supplied an already
        # validated manifest object rather than an isolated launcher path.
        return baseline
    configured_identity = surfaces.state.instance_manifest_path_identity
    if configured_identity and path_identity(configured_path) != configured_identity:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_PATH_CHANGED",
            "Isolated instance manifest path changed during session refresh",
        )
    candidate = load_instance_manifest(configured_path)
    immutable_mismatch = (
        candidate.schema_version != baseline.schema_version
        or candidate.profile_instance_id != baseline.profile_instance_id
        or candidate.rpc_host != baseline.rpc_host
        or candidate.rpc_port != baseline.rpc_port
        or path_identity(candidate.profile_path)
        != path_identity(baseline.profile_path)
        or path_identity(candidate.auth_secret_file)
        != path_identity(baseline.auth_secret_file)
        or candidate.expected_profile_path_fingerprint
        != baseline.expected_profile_path_fingerprint
        or candidate.created_at != baseline.created_at
        or candidate.rpc_host != surfaces.state.rpc_host
        or candidate.rpc_port != surfaces.state.rpc_port
        or candidate.profile_instance_id != surfaces.state.instance_id
        or (
            surfaces.state.auth_file is not None
            and path_identity(candidate.auth_secret_file)
            != path_identity(surfaces.state.auth_file)
        )
    )
    if immutable_mismatch:
        raise RpcAuthError(
            "INSTANCE_MANIFEST_IMMUTABLE_MISMATCH",
            "Isolated instance manifest changed immutable profile configuration",
        )
    candidate.require_complete_runtime()
    return candidate


def authenticate_connection(conn: FreeCADConnection, *, force: bool = False) -> None:
    """Refresh the short-lived RPC session without disturbing held leases."""
    from freecad_mcp import server

    if surfaces.state.instance_manifest is None or (not force and not session_needs_refresh()):
        return
    manifest = manifest_for_authentication()
    secret_path = surfaces.state.auth_file or manifest.auth_secret_file
    server.emit_event(
        "authentication",
        "authentication_started",
        payload={
            "forced_refresh": bool(force),
            "profile_instance_id": getattr(
                manifest, "profile_instance_id", surfaces.state.instance_id or "unknown"
            ),
        },
    )
    secret = load_profile_secret(secret_path)
    try:
        mcp_identity = make_mcp_runtime_identity(
            runtime_id=surfaces.state.mcp_instance_id,
            pid=surfaces.state.mcp_pid,
            process_started_at=surfaces.state.mcp_process_started_at,
            hostname=surfaces.state.mcp_host,
            client_build_id=build_id,
        )
        request = build_handshake_request_from_manifest(
            secret=secret,
            mcp=mcp_identity,
            manifest=manifest,
        )
        response = conn.invoke_rpc("handshake_v2", request, control=True)
        verified = verify_handshake_response_from_manifest(
            response,
            secret=secret,
            expected_client_nonce=request["client_nonce"],
            manifest=manifest,
        )
        # Commit the launcher-authorized runtime only after its HMAC response
        # proves every refreshed identity field.
        surfaces.state.instance_manifest = manifest
        surfaces.state.lease_manager.mark_connected(verified.session_token)
        surfaces.state.rpc_session_id = verified.session_id
        surfaces.state.rpc_session_expires_at = verified.session_expires_at
        surfaces.state.authenticated_manifest = verified.manifest
        conn.configure_lease_routing(
            surfaces.state.lease_manager,
            lambda name: surfaces.state.document_sessions.get(name),
        )
        conn.configure_session_refresher(
            lambda: refresh_authenticated_connection(conn)
        )
        conn.configure_stale_recovery(surfaces.stale_recovery)
        compatibility = compatibility_for_manifest(verified.manifest)
        surfaces.state.compatibility_warnings = compatibility["warnings"]
        server.emit_event(
            "authentication",
            "authentication_completed",
            payload={
                "mcp": build_info_dict(),
                "addon": {
                    "version": getattr(
                        verified.manifest, "addon_version", "unknown"
                    ),
                    "build_id": getattr(
                        verified.manifest, "addon_build_id", "unknown"
                    ),
                    "runtime_id": getattr(
                        verified.manifest, "addon_runtime_id", "unknown"
                    ),
                },
                "freecad": {
                    "version": getattr(
                        verified.manifest, "freecad_version", "unknown"
                    ),
                    "revision": getattr(
                        verified.manifest, "freecad_revision", "unknown"
                    ),
                    "pid": getattr(verified.manifest, "freecad_pid", None),
                },
                "rpc": {
                    "protocol_version": getattr(
                        verified.manifest, "protocol_version", protocol_version
                    ),
                    "features": list(
                        getattr(verified, "negotiated_features", ()) or ()
                    ),
                },
                "compatibility": compatibility,
            },
        )
    except Exception as exc:
        server.emit_event(
            "authentication",
            "authentication_failed",
            status=OutcomeStatus.FAILED.value,
            error_code=getattr(exc, "code", type(exc).__name__.upper()),
            payload={"exception_type": type(exc).__name__},
        )
        raise
    finally:
        secret = b""


def refresh_authenticated_connection(conn: FreeCADConnection) -> None:
    with surfaces.connection_lock:
        authenticate_connection(conn, force=True)

