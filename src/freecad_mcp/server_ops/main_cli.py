"""Main Cli (Phase 7 / 7D server_ops)."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable

from .._shared.protocol.manifest import (
    load_instance_manifest,
    make_mcp_runtime_identity,
)
from ..build_info import build_id
from ..instrumented_server import InstrumentedFastMCP
from ..server_state import ServerState
from . import surfaces


def validate_host(value: str) -> str:
    """Validate that *value* is a valid IP address or hostname.

    Used as the ``type`` callback for the ``--host`` argparse argument.
    Raises ``argparse.ArgumentTypeError`` on invalid input.
    """

    import validators

    if validators.ipv4(value) or validators.ipv6(value) or validators.hostname(value):
        return value
    raise argparse.ArgumentTypeError(
        f"Invalid host: '{value}'. Must be a valid IP address or hostname."
    )


def main(
    *,
    state: ServerState,
    mcp: InstrumentedFastMCP,
    path_identity: Callable[[str], str],
) -> None:
    """Run the MCP server"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only-text-feedback", action="store_true", help="Only return text feedback"
    )
    # The addon's RPC server binds IPv4 only, but "localhost" resolves to ::1 first on
    # Windows, costing ~2s per call to fail over to IPv4. Dial IPv4 directly.
    parser.add_argument(
        "--rpc-host",
        "--host",
        dest="rpc_host",
        type=validate_host,
        default=None,
        help=(
            "Host address of the FreeCAD RPC server. --host is a deprecated alias "
            "(default: manifest, FREECAD_MCP_RPC_HOST, or 127.0.0.1)"
        ),
    )
    parser.add_argument(
        "--rpc-port",
        "--port",
        dest="rpc_port",
        type=int,
        default=None,
        help=(
            "RPC port of the FreeCAD addon. --port is a deprecated alias "
            "(default: manifest, FREECAD_MCP_PORT, or 9875)"
        ),
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help=(
            "Expected FreeCAD instance id (default: FREECAD_MCP_INSTANCE_ID). When "
            "set, the client verifies the addon on --port reports the same id "
            "before driving it -- use it to pin an isolated parallel instance."
        ),
    )
    parser.add_argument(
        "--instance-manifest",
        default=None,
        help=(
            "Isolated instance-manifest.json (default: FREECAD_MCP_INSTANCE_MANIFEST)"
        ),
    )
    parser.add_argument(
        "--auth-file",
        default=None,
        help=(
            "Profile authentication secret path (default: manifest or "
            "FREECAD_MCP_AUTH_FILE); secret contents are never accepted on CLI"
        ),
    )
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    manifest_path = args.instance_manifest or os.environ.get(
        "FREECAD_MCP_INSTANCE_MANIFEST"
    )
    state.instance_manifest_path = (
        os.path.realpath(os.path.abspath(manifest_path)) if manifest_path else None
    )
    state.instance_manifest_path_identity = (
        path_identity(state.instance_manifest_path)
        if state.instance_manifest_path
        else None
    )
    state.instance_manifest = (
        load_instance_manifest(state.instance_manifest_path)
        if state.instance_manifest_path
        else None
    )
    env_host = os.environ.get("FREECAD_MCP_RPC_HOST")
    env_port = os.environ.get("FREECAD_MCP_PORT")
    requested_host = args.rpc_host or env_host
    requested_port = (
        args.rpc_port
        if args.rpc_port is not None
        else (int(env_port) if env_port else None)
    )
    requested_instance = args.instance_id or os.environ.get("FREECAD_MCP_INSTANCE_ID")
    requested_auth = args.auth_file or os.environ.get("FREECAD_MCP_AUTH_FILE")
    if state.instance_manifest is not None:
        manifest = state.instance_manifest
        if requested_host and requested_host != manifest.rpc_host:
            parser.error("--rpc-host does not match the instance manifest")
        if requested_port is not None and requested_port != manifest.rpc_port:
            parser.error("--rpc-port does not match the instance manifest")
        if requested_instance and requested_instance != manifest.profile_instance_id:
            parser.error("--instance-id does not match the instance manifest")
        if requested_auth and os.path.realpath(requested_auth) != os.path.realpath(
            manifest.auth_secret_file
        ):
            parser.error("--auth-file does not match the instance manifest")
        state.rpc_host = manifest.rpc_host
        state.rpc_port = manifest.rpc_port
        state.instance_id = manifest.profile_instance_id
        state.auth_file = manifest.auth_secret_file
    else:
        if requested_auth:
            parser.error(
                "--auth-file requires --instance-manifest so the authenticated "
                "handshake can verify the exact launched PID/runtime/build"
            )
        state.rpc_host = requested_host or "127.0.0.1"
        state.rpc_port = requested_port or 9875
        state.instance_id = requested_instance or None
        state.auth_file = requested_auth or None
    # MCP-process lease identity (distinct from the FreeCAD addon instance_id)
    state.mcp_client_label = os.environ.get("FREECAD_MCP_CLIENT", "freecad-mcp")
    mcp_identity = make_mcp_runtime_identity(client_build_id=build_id)
    state.mcp_instance_id = mcp_identity.runtime_id
    state.mcp_pid = mcp_identity.pid
    state.mcp_host = mcp_identity.hostname
    state.mcp_process_started_at = mcp_identity.process_started_at
    surfaces.logger.info(f"Only text feedback: {state.only_text_feedback}")
    surfaces.logger.info(
        f"Connecting to FreeCAD RPC server at: {state.rpc_host}:{state.rpc_port}"
        + (f" (instance {state.instance_id})" if state.instance_id else "")
    )
    surfaces.logger.info(
        f"MCP lease identity: {state.mcp_instance_id} "
        f"(client={state.mcp_client_label}, pid={state.mcp_pid}, host={state.mcp_host})"
    )
    mcp.run()
