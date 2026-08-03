"""Compatibility shims for the canonical vendored protocol types."""

from __future__ import annotations

import addon.FreeCADMCP.rpc_server.lease_protocol as addon_protocol
from freecad_mcp import rpc_auth


def test_addon_handshake_types_report_canonical_module_origins() -> None:
    prefix = "addon.FreeCADMCP._shared.protocol"
    assert addon_protocol.LeaseProtocolError.__module__ == f"{prefix}.protocol_error"
    assert addon_protocol.RuntimeManifest.__module__ == f"{prefix}.runtime_manifest"
    assert addon_protocol.McpRuntimeIdentity.__module__ == f"{prefix}.mcp_runtime_identity"
    assert addon_protocol.VerifiedHandshake.__module__ == f"{prefix}.verified_handshake"
    assert (
        addon_protocol.VerifiedHandshakeResponse.__module__
        == f"{prefix}.verified_handshake_response"
    )
    assert addon_protocol.SessionContext.__module__ == f"{prefix}.session_context"
    assert addon_protocol.LeaseCredential.__module__ == f"{prefix}.lease_credential"
    assert addon_protocol.OperationContext.__module__ == f"{prefix}.operation_context"
    assert addon_protocol.RequestEnvelope.__module__ == f"{prefix}.request_envelope"
    assert addon_protocol.ReplayCheck.__module__ == f"{prefix}.replay_check"
    assert addon_protocol.SessionManager.__module__ == f"{prefix}.session_manager"
    assert addon_protocol.RequestReplayCache.__module__ == (
        f"{prefix}.request_replay_cache"
    )


def test_addon_handshake_helpers_keep_legacy_import_paths() -> None:
    from addon.FreeCADMCP.rpc_server.lease_protocol_types.redaction import (
        redact_sensitive as defining_redact,
    )
    from addon.FreeCADMCP.rpc_server.lease_protocol_types.validation import (
        canonical_json_bytes as defining_canonical,
    )

    assert addon_protocol.redact_sensitive is defining_redact
    assert addon_protocol.canonical_json_bytes is defining_canonical


def test_client_handshake_types_report_canonical_module_origins() -> None:
    prefix = "freecad_mcp._shared.protocol"
    assert rpc_auth.RpcAuthError.__module__ == f"{prefix}.protocol_error"
    assert rpc_auth.McpRuntimeIdentity.__module__ == f"{prefix}.mcp_runtime_identity"
    assert rpc_auth.InstanceManifest.__module__ == f"{prefix}.instance_manifest"
    assert rpc_auth.RuntimeManifest.__module__ == f"{prefix}.runtime_manifest"
    assert (
        rpc_auth.VerifiedHandshakeResponse.__module__
        == f"{prefix}.verified_handshake_response"
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
