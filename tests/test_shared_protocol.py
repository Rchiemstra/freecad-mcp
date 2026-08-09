"""Contracts for the byte-identical authenticated protocol vendors."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from addon.FreeCADMCP._shared.protocol import constants as addon_constants
from addon.FreeCADMCP._shared.protocol.proof import _proof as addon_proof
from addon.FreeCADMCP._shared.protocol.validation import (
    canonical_json_bytes as addon_canonical_json_bytes,
)
from freecad_mcp._shared.protocol import constants as client_constants
from freecad_mcp._shared.protocol.proof import _proof as client_proof
from freecad_mcp._shared.protocol.validation import (
    canonical_json_bytes as client_canonical_json_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ADDON_VENDOR = ROOT / "addon" / "FreeCADMCP" / "_shared" / "protocol"
CLIENT_VENDOR = ROOT / "src" / "freecad_mcp" / "_shared" / "protocol"


def _vendor_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*.py"))
    }


@pytest.mark.unit
def test_protocol_vendors_are_byte_identical() -> None:
    addon = _vendor_files(ADDON_VENDOR)
    client = _vendor_files(CLIENT_VENDOR)

    assert addon
    assert addon == client
    assert {
        "handshake_request.py",
        "handshake_response.py",
        "proof.py",
        "request_replay_cache.py",
        "session_manager.py",
        "validation.py",
    } <= addon.keys()


@pytest.mark.unit
def test_protocol_vendors_use_only_stdlib_and_local_leaves() -> None:
    for relative, source in _vendor_files(ADDON_VENDOR).items():
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.split(".", maxsplit=1)[0] in sys.stdlib_module_names
                    for alias in node.names
                ), (relative, ast.unparse(node))
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or "").split(".", maxsplit=1)[0] in (
                    sys.stdlib_module_names
                ), (relative, ast.unparse(node))


@pytest.mark.unit
def test_canonicalization_and_signing_match_across_vendors() -> None:
    payload = {
        "a": {"unicode": "é", "finite": 1.25},
        "z": [3, True, None],
    }
    addon_encoded = addon_canonical_json_bytes(payload)
    client_encoded = client_canonical_json_bytes(payload)

    assert addon_encoded == client_encoded
    assert addon_proof(
        b"s" * 32, addon_constants._REQUEST_PROOF_DOMAIN, payload
    ) == client_proof(b"s" * 32, client_constants._REQUEST_PROOF_DOMAIN, payload)
    assert addon_constants.PROTOCOL_VERSION == client_constants.PROTOCOL_VERSION == 2
    assert (
        addon_constants.MAX_HANDSHAKE_BYTES
        == client_constants.MAX_HANDSHAKE_BYTES
    )


@pytest.mark.unit
def test_runtime_manifest_normalizes_equivalent_utc_spellings() -> None:
    from addon.FreeCADMCP._shared.protocol.mcp_runtime_identity import (
        McpRuntimeIdentity,
    )
    from addon.FreeCADMCP._shared.protocol.runtime_manifest import RuntimeManifest

    manifest = RuntimeManifest(
        profile_id="profile-a",
        addon_runtime_id="8c897b64-0f04-4e09-9f80-2873d4527b7f",
        freecad_pid=4321,
        freecad_process_started_at="2026-07-22T10:00:00Z",
        boot_id="boot-a",
        rpc_host="127.0.0.1",
        rpc_port=9876,
        freecad_version="1.0.0",
        freecad_revision="abc123",
        addon_version="0.1.20",
        addon_build_id="build-a",
        profile_path_fingerprint="sha256:0123456789abcdef",
    )

    assert manifest.freecad_process_started_at == "2026-07-22T10:00:00.000000Z"
    identity = McpRuntimeIdentity(
        runtime_id="3201517e-5664-4ee0-9168-81b46f29f0e0",
        pid=8765,
        process_started_at="2026-07-22T10:00:00Z",
        hostname="test-host",
        client_build_id="client-build-a",
    )
    assert identity.process_started_at == "2026-07-22T10:00:00.000000Z"
