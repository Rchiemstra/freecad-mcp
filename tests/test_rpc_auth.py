"""MCP-side RPC authentication compatibility tests."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
import os
import uuid

import pytest

from addon.FreeCADMCP.rpc_server import lease_protocol as addon_protocol
from freecad_mcp import rpc_auth


SECRET = b"a" * 32
NOW = "2026-07-22T10:00:00.000000Z"
MCP_RUNTIME_ID = "3201517e-5664-4ee0-9168-81b46f29f0e0"
ADDON_RUNTIME_ID = "8c897b64-0f04-4e09-9f80-2873d4527b7f"
CLIENT_NONCE = "Y2xpZW50LW5vbmNlLTAxMjM0NTY3ODkwMTIzNDU2Nzg5MA"


def _addon_manifest(**overrides):
    values = {
        "profile_id": "isolated-profile-a",
        "addon_runtime_id": ADDON_RUNTIME_ID,
        "freecad_pid": 4321,
        "freecad_process_started_at": NOW,
        "boot_id": "boot-a",
        "rpc_host": "127.0.0.1",
        "rpc_port": 9876,
        "freecad_version": "1.0.0",
        "freecad_revision": "abc123",
        "addon_version": "0.1.20",
        "addon_build_id": "build-a",
        "profile_path_fingerprint": "sha256:0123456789abcdef",
    }
    values.update(overrides)
    return addon_protocol.make_runtime_manifest(**values)


def _client_identity(**overrides):
    values = {
        "runtime_id": MCP_RUNTIME_ID,
        "pid": 8765,
        "process_started_at": NOW,
        "hostname": "test-host",
        "client_build_id": "client-build-a",
    }
    values.update(overrides)
    return rpc_auth.McpRuntimeIdentity(**values)


def _client_request(manifest=None, **overrides):
    manifest = manifest or _addon_manifest()
    values = {
        "secret": SECRET,
        "mcp": _client_identity(),
        "expected_profile_id": manifest.profile_id,
        "expected_freecad_pid": manifest.freecad_pid,
        "expected_freecad_process_started_at": manifest.freecad_process_started_at,
        "expected_addon_runtime_id": manifest.addon_runtime_id,
        "expected_boot_id": manifest.boot_id,
        "expected_rpc_host": manifest.rpc_host,
        "expected_rpc_port": manifest.rpc_port,
        "expected_protocol_version": manifest.protocol_version,
        "expected_protocol_features": manifest.features,
        "expected_addon_version": manifest.addon_version,
        "expected_addon_build_id": manifest.addon_build_id,
        "expected_freecad_version": manifest.freecad_version,
        "expected_freecad_revision": manifest.freecad_revision,
        "expected_profile_path_fingerprint": manifest.profile_path_fingerprint,
        "client_nonce": CLIENT_NONCE,
    }
    values.update(overrides)
    return rpc_auth.build_handshake_request(**values)


def _response_expectations(manifest, request):
    return {
        "expected_client_nonce": request["client_nonce"],
        "expected_profile_id": manifest.profile_id,
        "expected_freecad_pid": manifest.freecad_pid,
        "expected_freecad_process_started_at": manifest.freecad_process_started_at,
        "expected_addon_runtime_id": manifest.addon_runtime_id,
        "expected_boot_id": manifest.boot_id,
        "expected_rpc_host": manifest.rpc_host,
        "expected_rpc_port": manifest.rpc_port,
        "expected_protocol_version": manifest.protocol_version,
        "expected_protocol_features": manifest.features,
        "expected_addon_version": manifest.addon_version,
        "expected_addon_build_id": manifest.addon_build_id,
        "expected_freecad_version": manifest.freecad_version,
        "expected_freecad_revision": manifest.freecad_revision,
        "expected_profile_path_fingerprint": manifest.profile_path_fingerprint,
    }


def _perform_round_trip(manifest=None):
    manifest = manifest or _addon_manifest()
    request = _client_request(manifest)
    manager = addon_protocol.SessionManager(manifest=manifest, secret=SECRET)
    response = manager.perform_handshake(request)
    verified = rpc_auth.verify_handshake_response(
        response,
        secret=SECRET,
        **_response_expectations(manifest, request),
    )
    return manager, request, response, verified


def test_canonical_json_matches_addon_byte_for_byte():
    payload = {"z": [3, True, None], "a": {"unicode": "é", "value": 1.25}}
    assert rpc_auth.canonical_json_bytes(
        payload
    ) == addon_protocol.canonical_json_bytes(payload)


def test_client_request_is_accepted_and_verified_by_addon():
    manifest = _addon_manifest()
    request = _client_request(manifest)

    verified = addon_protocol.verify_handshake_request(
        request, secret=SECRET, manifest=manifest
    )

    assert verified.client_nonce == CLIENT_NONCE
    assert verified.mcp.runtime_id == MCP_RUNTIME_ID
    assert verified.mcp.pid == 8765
    assert verified.mcp.client_build_id == "client-build-a"


def test_signed_request_asserts_the_complete_runtime_manifest():
    request = _client_request()
    assert set(request["expected_server"]) == {
        "profile_id",
        "freecad_pid",
        "freecad_process_started_at",
        "addon_runtime_id",
        "boot_id",
        "rpc_host",
        "rpc_port",
        "protocol_version",
        "features",
        "addon_version",
        "addon_build_id",
        "freecad_version",
        "freecad_revision",
        "profile_path_fingerprint",
    }


@pytest.mark.parametrize(
    "field",
    [
        "freecad_process_started_at",
        "addon_runtime_id",
        "boot_id",
        "rpc_host",
        "rpc_port",
        "protocol_version",
        "features",
        "addon_version",
        "addon_build_id",
        "freecad_version",
        "freecad_revision",
        "profile_path_fingerprint",
    ],
)
def test_addon_rejects_signed_handshake_with_skipped_runtime_field(field):
    request = _client_request()
    del request["expected_server"][field]
    request = addon_protocol.sign_handshake_request(request, SECRET)

    with pytest.raises(addon_protocol.LeaseProtocolError) as raised:
        addon_protocol.SessionManager(
            manifest=_addon_manifest(), secret=SECRET
        ).perform_handshake(request)

    assert raised.value.code == "MALFORMED_PAYLOAD"


def test_addon_response_is_accepted_with_every_runtime_expectation():
    manager, request, response, verified = _perform_round_trip()

    assert response["client_nonce"] == request["client_nonce"]
    assert verified.manifest.profile_id == "isolated-profile-a"
    assert verified.manifest.freecad_pid == 4321
    assert verified.manifest.addon_runtime_id == ADDON_RUNTIME_ID
    assert verified.manifest.endpoint == "127.0.0.1:9876"
    assert verified.manifest.addon_build_id == "build-a"
    assert verified.manifest.freecad_version == "1.0.0"
    assert {
        "authenticated_sessions",
        "lease_credentials_v2",
        "runtime_binding",
    }.issubset(verified.negotiated_features)

    context = manager.authenticate(
        verified.session_token, mcp_runtime_id=MCP_RUNTIME_ID
    )
    assert context.session_id == verified.session_id


def test_client_and_addon_request_proofs_are_identical():
    manifest = _addon_manifest()
    client = _client_request(manifest)
    addon = addon_protocol.build_handshake_request(
        secret=SECRET,
        mcp=addon_protocol.McpRuntimeIdentity(**_client_identity().to_dict()),
        expected_profile_id=manifest.profile_id,
        expected_freecad_pid=manifest.freecad_pid,
        expected_freecad_process_started_at=manifest.freecad_process_started_at,
        expected_addon_runtime_id=manifest.addon_runtime_id,
        expected_boot_id=manifest.boot_id,
        expected_rpc_host=manifest.rpc_host,
        expected_rpc_port=manifest.rpc_port,
        expected_protocol_version=manifest.protocol_version,
        expected_protocol_features=manifest.features,
        expected_addon_version=manifest.addon_version,
        expected_addon_build_id=manifest.addon_build_id,
        expected_freecad_version=manifest.freecad_version,
        expected_freecad_revision=manifest.freecad_revision,
        expected_profile_path_fingerprint=manifest.profile_path_fingerprint,
        client_nonce=CLIENT_NONCE,
    )

    assert client == addon


@pytest.mark.parametrize(
    ("expectation", "wrong_value"),
    [
        ("expected_profile_id", "other-profile"),
        ("expected_freecad_pid", 98765),
        ("expected_addon_runtime_id", "bd2463a0-20c0-48bc-98db-435e272cfe48"),
        ("expected_freecad_process_started_at", "2026-07-22T10:00:01Z"),
        ("expected_boot_id", "other-boot"),
        ("expected_rpc_host", "localhost"),
        ("expected_rpc_port", 9999),
        (
            "expected_protocol_features",
            tuple(sorted(rpc_auth.REQUIRED_PROTOCOL_FEATURES)),
        ),
        ("expected_addon_version", "9.9.9"),
        ("expected_addon_build_id", "other-build"),
        ("expected_freecad_version", "2.0.0"),
        ("expected_freecad_revision", "other-revision"),
        ("expected_profile_path_fingerprint", "sha256:other"),
    ],
)
def test_response_expectation_mismatch_fails_closed(expectation, wrong_value):
    _manager, request, response, _verified = _perform_round_trip()
    manifest = _addon_manifest()
    expectations = _response_expectations(manifest, request)
    expectations[expectation] = wrong_value

    with pytest.raises(rpc_auth.RpcAuthError) as raised:
        rpc_auth.verify_handshake_response(response, secret=SECRET, **expectations)

    assert raised.value.code == "INSTANCE_MISMATCH"
    assert verified_token(response) not in str(raised.value)


def test_protocol_expectation_and_response_version_must_be_v2():
    _manager, request, response, _verified = _perform_round_trip()
    response = copy.deepcopy(response)
    response["protocol_version"] = 1
    response = addon_protocol.sign_handshake_response(response, SECRET)

    with pytest.raises(rpc_auth.RpcAuthError) as raised:
        rpc_auth.verify_handshake_response(
            response,
            secret=SECRET,
            **_response_expectations(_addon_manifest(), request),
        )

    assert raised.value.code == "UNSUPPORTED_PROTOCOL"


@pytest.mark.parametrize("offset", [timedelta(seconds=-1), timedelta(hours=2)])
def test_signed_expired_or_excessively_long_session_is_rejected(offset):
    _manager, request, response, _verified = _perform_round_trip()
    response = copy.deepcopy(response)
    response["session_expires_at"] = (
        (datetime.now(timezone.utc) + offset).isoformat().replace("+00:00", "Z")
    )
    response = addon_protocol.sign_handshake_response(response, SECRET)

    with pytest.raises(rpc_auth.RpcAuthError) as raised:
        rpc_auth.verify_handshake_response(
            response,
            secret=SECRET,
            **_response_expectations(_addon_manifest(), request),
        )

    assert raised.value.code == "INVALID_SESSION_EXPIRY"
    assert verified_token(response) not in str(raised.value)


def test_tampered_or_wrong_secret_response_never_exposes_credentials():
    _manager, request, response, _verified = _perform_round_trip()
    token = verified_token(response)
    tampered = copy.deepcopy(response)
    tampered["manifest"]["rpc_port"] = 12345

    for value, secret in ((tampered, SECRET), (response, b"x" * 32)):
        with pytest.raises(rpc_auth.RpcAuthError) as raised:
            rpc_auth.verify_handshake_response(
                value,
                secret=secret,
                **_response_expectations(_addon_manifest(), request),
            )
        assert raised.value.code == "AUTHENTICATION_FAILED"
        assert token not in str(raised.value)
        assert SECRET.hex() not in str(raised.value)


def test_instance_manifest_loads_secret_and_drives_round_trip(tmp_path):
    secret_path = tmp_path / "profile.auth"
    secret_path.write_bytes(SECRET)
    if os.name != "nt":
        secret_path.chmod(0o600)
    manifest_path = tmp_path / "instance-manifest.json"
    instance_payload = {
        "schema_version": 1,
        "rpc_host": "127.0.0.1",
        "rpc_port": 9876,
        "profile_instance_id": "isolated-profile-a",
        "profile_path": str(tmp_path),
        "auth_secret_file": str(secret_path),
        "expected_freecad_pid": 4321,
        "expected_freecad_process_started_at": NOW,
        "expected_addon_runtime_id": ADDON_RUNTIME_ID,
        "expected_boot_id": "boot-a",
        "expected_protocol_version": 2,
        "expected_protocol_features": list(_addon_manifest().features),
        "expected_addon_version": "0.1.20",
        "expected_addon_build_id": "build-a",
        "expected_freecad_version": "1.0.0",
        "expected_freecad_revision": "abc123",
        "expected_profile_path_fingerprint": "sha256:0123456789abcdef",
        "created_at": NOW,
    }
    manifest_path.write_text(json.dumps(instance_payload), encoding="utf-8")

    instance = rpc_auth.load_instance_manifest(manifest_path)
    loaded_secret = instance.load_secret()
    request = rpc_auth.build_handshake_request_from_manifest(
        secret=loaded_secret,
        mcp=_client_identity(),
        manifest=instance,
        client_nonce=CLIENT_NONCE,
    )
    response = addon_protocol.SessionManager(
        manifest=_addon_manifest(), secret=SECRET
    ).perform_handshake(request)
    verified = rpc_auth.verify_handshake_response_from_manifest(
        response,
        secret=loaded_secret,
        expected_client_nonce=request["client_nonce"],
        manifest=instance,
    )

    assert verified.manifest.addon_runtime_id == ADDON_RUNTIME_ID
    assert verified.manifest.freecad_process_started_at == NOW
    assert str(secret_path) not in repr(instance)
    assert verified.session_token not in repr(verified)
    assert SECRET not in repr(instance).encode()


def test_incomplete_instance_manifest_cannot_start_handshake(tmp_path):
    secret_path = tmp_path / "profile.auth"
    secret_path.write_bytes(SECRET)
    if os.name != "nt":
        secret_path.chmod(0o600)
    payload = {
        "schema_version": 1,
        "rpc_host": "127.0.0.1",
        "rpc_port": 9876,
        "profile_instance_id": "isolated-profile-a",
        "profile_path": str(tmp_path),
        "auth_secret_file": str(secret_path),
        "expected_freecad_pid": None,
        "expected_freecad_process_started_at": None,
        "expected_addon_runtime_id": None,
        "expected_boot_id": None,
        "expected_protocol_version": None,
        "expected_protocol_features": None,
        "expected_addon_version": None,
        "expected_addon_build_id": None,
        "expected_freecad_version": None,
        "expected_freecad_revision": None,
        "expected_profile_path_fingerprint": None,
        "created_at": NOW,
    }
    manifest = rpc_auth.InstanceManifest.from_dict(payload)

    with pytest.raises(rpc_auth.RpcAuthError) as raised:
        rpc_auth.build_handshake_request_from_manifest(
            secret=SECRET, mcp=_client_identity(), manifest=manifest
        )

    assert raised.value.code == "INCOMPLETE_INSTANCE_MANIFEST"


def test_manifest_unknown_fields_and_noncanonical_values_are_rejected(tmp_path):
    path = tmp_path / "instance-manifest.json"
    path.write_text('{"schema_version": 1, "secret": "do-not-log"}', encoding="utf-8")

    with pytest.raises(rpc_auth.RpcAuthError) as raised:
        rpc_auth.load_instance_manifest(path)

    assert raised.value.code == "MALFORMED_PAYLOAD"
    assert "do-not-log" not in str(raised.value)


def test_mcp_runtime_factory_uses_one_valid_process_identity():
    identity = rpc_auth.make_mcp_runtime_identity(client_build_id="freecad-mcp/0.1.20")

    assert uuid.UUID(identity.runtime_id).int != 0
    assert identity.pid == os.getpid()
    assert identity.process_started_at.endswith("Z")


def verified_token(response):
    """Keep assertions readable without ever interpolating tokens in errors."""

    return response["session_token"]
