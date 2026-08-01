"""§3.3 shim checks for handshake twin leaf types (workstream 1G)."""

from __future__ import annotations

import addon.FreeCADMCP.rpc_server.lease_protocol as addon_protocol
from freecad_mcp import rpc_auth


def test_addon_handshake_types_keep_legacy_module_names() -> None:
    assert addon_protocol.LeaseProtocolError.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.RuntimeManifest.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.McpRuntimeIdentity.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.VerifiedHandshake.__module__ == "rpc_server.lease_protocol"
    assert (
        addon_protocol.VerifiedHandshakeResponse.__module__
        == "rpc_server.lease_protocol"
    )
    assert addon_protocol.SessionContext.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.LeaseCredential.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.OperationContext.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.RequestEnvelope.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.ReplayCheck.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.SessionManager.__module__ == "rpc_server.lease_protocol"
    assert addon_protocol.RequestReplayCache.__module__ == "rpc_server.lease_protocol"


def test_addon_handshake_helpers_keep_legacy_import_paths() -> None:
    from addon.FreeCADMCP.rpc_server.lease_protocol_types.redaction import (
        redact_sensitive as defining_redact,
    )
    from addon.FreeCADMCP.rpc_server.lease_protocol_types.validation import (
        canonical_json_bytes as defining_canonical,
    )

    assert addon_protocol.redact_sensitive is defining_redact
    assert addon_protocol.canonical_json_bytes is defining_canonical


def test_client_handshake_types_keep_legacy_module_names() -> None:
    assert rpc_auth.RpcAuthError.__module__ == "freecad_mcp.rpc_auth"
    assert rpc_auth.McpRuntimeIdentity.__module__ == "freecad_mcp.rpc_auth"
    assert rpc_auth.InstanceManifest.__module__ == "freecad_mcp.rpc_auth"
    assert rpc_auth.RuntimeManifest.__module__ == "freecad_mcp.rpc_auth"
    assert (
        rpc_auth.VerifiedHandshakeResponse.__module__ == "freecad_mcp.rpc_auth"
    )


def test_addon_handshake_constants_keep_legacy_import_paths() -> None:
    from addon.FreeCADMCP.rpc_server.lease_protocol_types import constants as defining

    for name in (
        "PROTOCOL_NAME",
        "HMAC_ALGORITHM",
        "MAX_ENVELOPE_BYTES",
        "MAX_LEASE_CREDENTIALS",
        "MAX_PARAMS_DEPTH",
    ):
        assert hasattr(addon_protocol, name)
        assert getattr(addon_protocol, name) is getattr(defining, name)


def test_client_handshake_constants_keep_legacy_import_paths() -> None:
    from freecad_mcp.rpc_auth_types import constants as defining

    for name in (
        "PROTOCOL_NAME",
        "HMAC_ALGORITHM",
        "INSTANCE_MANIFEST_SCHEMA_VERSION",
        "MAX_JSON_DEPTH",
        "MAX_SECRET_FILE_BYTES",
        "MIN_SECRET_BYTES",
    ):
        assert hasattr(rpc_auth, name)
        assert getattr(rpc_auth, name) is getattr(defining, name)

    assert rpc_auth.canonical_json_bytes is not None
    from freecad_mcp.rpc_auth_types.validation import canonical_json_bytes as defining_fn

    assert rpc_auth.canonical_json_bytes is defining_fn
