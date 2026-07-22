"""Authenticated lease protocol-v2 tests (stdlib-only protocol layer)."""

from __future__ import annotations

import copy
import os
import uuid
import pytest

from addon.FreeCADMCP.rpc_server.lease_protocol import (
    LeaseProtocolError,
    McpRuntimeIdentity,
    RequestEnvelope,
    RequestReplayCache,
    SessionManager,
    build_handshake_request,
    canonical_json_bytes,
    create_profile_secret,
    load_profile_secret,
    make_runtime_manifest,
    public_error,
    redact_sensitive,
    sign_handshake_request,
    verify_handshake_response,
)


SECRET = b"p" * 32
NOW = "2026-07-22T10:00:00.000000Z"


def _manifest(**overrides):
    values = {
        "profile_id": "isolated-profile-a",
        "addon_runtime_id": "8c897b64-0f04-4e09-9f80-2873d4527b7f",
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
    return make_runtime_manifest(**values)


def _mcp(**overrides):
    values = {
        "runtime_id": "3201517e-5664-4ee0-9168-81b46f29f0e0",
        "pid": 8765,
        "process_started_at": NOW,
        "hostname": "test-host",
        "client_build_id": "client-build-a",
    }
    values.update(overrides)
    return McpRuntimeIdentity(**values)


def _request(manifest=None, **overrides):
    manifest = manifest or _manifest()
    values = {
        "secret": SECRET,
        "mcp": _mcp(),
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
    values.update(overrides)
    return build_handshake_request(**values)


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


def _handshake(*, clock=None, ttl=300.0):
    manifest = _manifest()
    kwargs = {}
    if clock is not None:
        kwargs["monotonic"] = clock
    manager = SessionManager(
        manifest=manifest,
        secret=SECRET,
        session_ttl_seconds=ttl,
        **kwargs,
    )
    request = _request(manifest)
    response = manager.perform_handshake(request)
    verified = verify_handshake_response(
        response,
        secret=SECRET,
        **_response_expectations(manifest, request),
    )
    return manager, request, response, verified


def _envelope(token, runtime_id=None, **overrides):
    payload = {
        "protocol_version": 2,
        "request_id": str(uuid.uuid4()),
        "session_token": token,
        "mcp_runtime_id": runtime_id or _mcp().runtime_id,
        "method": "create_pad",
        "params": {"document": "Model", "length": 10.0},
        "lease_credentials": [
            {
                "lease_id": str(uuid.uuid4()),
                "document_session_uuid": str(uuid.uuid4()),
                "generation": 3,
                "token": "L" * 43,
            }
        ],
        "operation": {"name": "Create Pad", "task_id": str(uuid.uuid4())},
    }
    payload.update(overrides)
    return payload


def test_authenticated_handshake_and_bound_envelope_succeed():
    manager, request, response, verified = _handshake()

    assert response["manifest"]["endpoint"] == "127.0.0.1:9876"
    assert response["manifest"]["freecad_pid"] == 4321
    assert response["manifest"]["freecad_process_started_at"] == NOW
    assert response["manifest"]["profile_id"] == "isolated-profile-a"
    assert response["manifest"]["addon_build_id"] == "build-a"
    assert response["client_nonce"] == request["client_nonce"]
    assert verified.manifest.addon_runtime_id == _manifest().addon_runtime_id

    context, envelope = manager.authenticate_envelope(
        _envelope(verified.session_token)
    )
    assert context.session_id == verified.session_id
    assert context.mcp.runtime_id == _mcp().runtime_id
    assert envelope.method == "create_pad"
    assert envelope.lease_credentials[0].generation == 3


def test_manifest_accepts_realistic_freecad_revision_text():
    manifest = _manifest(freecad_revision="33771 (Git)")
    assert manifest.freecad_revision == "33771 (Git)"


def test_canonical_json_is_stable_and_rejects_non_json_values():
    assert canonical_json_bytes({"z": 1, "a": [True, "é"]}) == canonical_json_bytes(
        {"a": [True, "é"], "z": 1}
    )
    with pytest.raises(LeaseProtocolError, match="INVALID_JSON_VALUE"):
        canonical_json_bytes({"bad": object()})


def test_bad_handshake_hmac_is_rejected_without_echoing_proof():
    request = _request()
    request["proof"] = "hmac-sha256:" + "0" * 64
    manager = SessionManager(manifest=_manifest(), secret=SECRET)

    with pytest.raises(LeaseProtocolError) as raised:
        manager.perform_handshake(request)

    assert raised.value.code == "AUTHENTICATION_FAILED"
    assert request["proof"] not in str(raised.value)


def test_tampered_handshake_response_proof_is_rejected():
    _manager, request, response, _verified = _handshake()
    response["manifest"]["rpc_port"] = 9999

    with pytest.raises(LeaseProtocolError) as raised:
        verify_handshake_response(
            response,
            secret=SECRET,
            **_response_expectations(_manifest(), request),
        )

    assert raised.value.code == "AUTHENTICATION_FAILED"


def test_bad_nonce_is_rejected_after_valid_signature():
    request = _request()
    request["client_nonce"] = "too-short"
    request = sign_handshake_request(request, SECRET)

    with pytest.raises(LeaseProtocolError) as raised:
        SessionManager(manifest=_manifest(), secret=SECRET).perform_handshake(request)

    assert raised.value.code == "INVALID_NONCE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profile_id", "wrong-profile"),
        ("freecad_pid", 9999),
        ("freecad_process_started_at", "2026-07-22T10:00:01.000000Z"),
        ("addon_runtime_id", "bd2463a0-20c0-48bc-98db-435e272cfe48"),
        ("boot_id", "wrong-boot"),
        ("rpc_host", "localhost"),
        ("rpc_port", 9988),
        ("protocol_version", 1),
        (
            "features",
            sorted(
                {
                    "authenticated_sessions",
                    "lease_credentials_v2",
                    "runtime_binding",
                }
            ),
        ),
        ("addon_version", "9.9.9"),
        ("addon_build_id", "wrong-build"),
        ("freecad_version", "9.9.9"),
        ("freecad_revision", "wrong-revision"),
        ("profile_path_fingerprint", "sha256:wrong"),
    ],
)
def test_expected_runtime_mismatch_is_rejected(field, value):
    request = _request()
    request["expected_server"][field] = value
    request = sign_handshake_request(request, SECRET)

    with pytest.raises(LeaseProtocolError) as raised:
        SessionManager(manifest=_manifest(), secret=SECRET).perform_handshake(request)

    assert raised.value.code == "INSTANCE_MISMATCH"


def test_bad_protocol_version_is_rejected():
    request = _request()
    request["protocol_version"] = 1
    request = sign_handshake_request(request, SECRET)

    with pytest.raises(LeaseProtocolError) as raised:
        SessionManager(manifest=_manifest(), secret=SECRET).perform_handshake(request)

    assert raised.value.code == "UNSUPPORTED_PROTOCOL"


def test_handshake_nonce_cannot_be_replayed():
    manager = SessionManager(manifest=_manifest(), secret=SECRET)
    request = _request()
    manager.perform_handshake(request)

    with pytest.raises(LeaseProtocolError) as raised:
        manager.perform_handshake(request)

    assert raised.value.code == "HANDSHAKE_REPLAY"


def test_session_expires_using_monotonic_time():
    now = [100.0]
    manager, request_payload, _response, verified = _handshake(
        clock=lambda: now[0], ttl=5.0
    )
    manager.authenticate(
        verified.session_token, mcp_runtime_id=_mcp().runtime_id
    )
    now[0] = 105.0

    with pytest.raises(LeaseProtocolError) as raised:
        manager.authenticate(
            verified.session_token, mcp_runtime_id=_mcp().runtime_id
        )

    assert raised.value.code == "SESSION_EXPIRED"

    # Session cleanup must not make its signed client nonce reusable within
    # the same FreeCAD addon runtime.
    manager.prune_expired()
    with pytest.raises(LeaseProtocolError) as raised:
        manager.perform_handshake(request_payload)
    assert raised.value.code == "HANDSHAKE_REPLAY"


def test_session_revocation_and_runtime_binding_are_enforced():
    manager, _request_payload, _response, verified = _handshake()

    with pytest.raises(LeaseProtocolError) as raised:
        manager.authenticate(
            verified.session_token,
            mcp_runtime_id="bd2463a0-20c0-48bc-98db-435e272cfe48",
        )
    assert raised.value.code == "SESSION_BINDING_MISMATCH"

    assert manager.revoke(session_id=verified.session_id, reason="test") is True
    with pytest.raises(LeaseProtocolError) as raised:
        manager.authenticate(
            verified.session_token, mcp_runtime_id=_mcp().runtime_id
        )
    assert raised.value.code == "SESSION_REVOKED"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("request_id"),
        lambda value: value.update(protocol_version=1),
        lambda value: value.update(request_id="not-a-uuid"),
        lambda value: value.update(session_token="short"),
        lambda value: value.update(method="Create Pad"),
        lambda value: value.update(params=[]),
        lambda value: value.update(lease_credentials="not-a-list"),
        lambda value: value["lease_credentials"][0].update(generation=0),
        lambda value: value.update(unknown=True),
    ],
)
def test_malformed_request_envelopes_are_rejected(mutation):
    _manager, _request_payload, _response, verified = _handshake()
    payload = _envelope(verified.session_token)
    mutation(payload)

    with pytest.raises(LeaseProtocolError):
        RequestEnvelope.from_dict(payload)


def test_transport_and_envelope_runtime_must_match():
    manager, _request_payload, _response, verified = _handshake()
    payload = _envelope(verified.session_token)

    with pytest.raises(LeaseProtocolError) as raised:
        manager.authenticate_envelope(
            payload,
            transport_mcp_runtime_id="bd2463a0-20c0-48bc-98db-435e272cfe48",
        )

    assert raised.value.code == "SESSION_BINDING_MISMATCH"


def test_replay_cache_returns_completed_response_and_rejects_changed_request():
    _manager, _request_payload, _response, verified = _handshake()
    envelope = RequestEnvelope.from_dict(_envelope(verified.session_token))
    cache = RequestReplayCache()

    runtime_id = _mcp().runtime_id
    assert cache.claim(runtime_id, envelope).status == "new"
    assert cache.claim(runtime_id, envelope).status == "in_progress"
    cache.complete(runtime_id, envelope, {"ok": True, "value": 3})
    replay = cache.claim(runtime_id, envelope)
    assert replay.status == "completed"
    assert replay.response == {"ok": True, "value": 3}

    changed = RequestEnvelope.from_dict(
        {
            **_envelope(verified.session_token),
            "request_id": envelope.request_id,
            "params": {"document": "Different"},
        }
    )
    with pytest.raises(LeaseProtocolError) as raised:
        cache.claim(runtime_id, changed)
    assert raised.value.code == "REQUEST_ID_REUSE"


def test_replay_cache_journals_late_gui_completion():
    _manager, _request_payload, _response, verified = _handshake()
    envelope = RequestEnvelope.from_dict(_envelope(verified.session_token))
    cache = RequestReplayCache()
    runtime_id = _mcp().runtime_id
    assert cache.claim(runtime_id, envelope).status == "new"
    cache.complete(
        runtime_id,
        envelope,
        {"ok": False, "error": {"code": "GUI_TIMEOUT"}},
    )

    late = {"ok": True, "late_completion": True, "result": {"success": True}}
    assert cache.journal_completion(
        runtime_id, envelope.request_id, late
    )
    assert cache.status(runtime_id, envelope.request_id).response == late
    assert not cache.journal_completion(
        runtime_id, str(uuid.uuid4()), late
    )


def test_replay_semantics_survive_session_refresh_and_normalize_generated_hmac():
    runtime_id = _mcp().runtime_id
    request_id = str(uuid.uuid4())
    lease_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    base = {
        "protocol_version": 2,
        "request_id": request_id,
        "mcp_runtime_id": runtime_id,
        "method": "execute_code",
        "params": {
            "code": "doc.addObject('Part::Feature', 'Box')",
            "options": {
                "document": "Model",
                "affected_documents": ["Model"],
                "generated_operation": True,
                "operation_id": "partdesign.create-box",
                "operation_signature": "hmac-sha256:" + "1" * 64,
            },
        },
        "lease_credentials": [
            {
                "lease_id": lease_id,
                "document_session_uuid": document_id,
                "generation": 4,
                "token": "L" * 43,
            }
        ],
        "operation": {"name": "Create box", "task_id": task_id},
    }
    first = RequestEnvelope.from_dict({**copy.deepcopy(base), "session_token": "A" * 43})
    refreshed_payload = copy.deepcopy(base)
    refreshed_payload["session_token"] = "B" * 43
    refreshed_payload["params"]["options"]["operation_signature"] = (
        "hmac-sha256:" + "2" * 64
    )
    refreshed = RequestEnvelope.from_dict(refreshed_payload)
    cache = RequestReplayCache()

    assert first.semantic_fingerprint() == refreshed.semantic_fingerprint()
    assert cache.claim(runtime_id, first, pin_to_owner_leases=True).status == "new"
    cache.complete(runtime_id, first, {"ok": True, "result": {"success": True}})
    replay = cache.claim(runtime_id, refreshed, pin_to_owner_leases=True)
    assert replay.status == "completed"


def test_replay_rejects_changed_multi_document_credential_across_sessions():
    runtime_id = _mcp().runtime_id
    payload = _envelope("A" * 43)
    payload["lease_credentials"].append(
        {
            "lease_id": str(uuid.uuid4()),
            "document_session_uuid": str(uuid.uuid4()),
            "generation": 8,
            "token": "M" * 43,
        }
    )
    first = RequestEnvelope.from_dict(payload)
    cache = RequestReplayCache()
    cache.claim(runtime_id, first, pin_to_owner_leases=True)
    cache.complete(runtime_id, first, {"ok": True})

    changed_payload = copy.deepcopy(payload)
    changed_payload["session_token"] = "B" * 43
    changed_payload["lease_credentials"][1]["generation"] = 9
    changed = RequestEnvelope.from_dict(changed_payload)
    with pytest.raises(LeaseProtocolError) as raised:
        cache.claim(runtime_id, changed, pin_to_owner_leases=True)
    assert raised.value.code == "REQUEST_ID_REUSE"


def test_pinned_replay_compacts_after_ttl_and_is_not_evicted_until_release():
    now = [10.0]
    active = { _mcp().runtime_id }
    runtime_id = _mcp().runtime_id
    envelope = RequestEnvelope.from_dict(_envelope("S" * 43))
    cache = RequestReplayCache(
        ttl_seconds=5,
        monotonic=lambda: now[0],
        owner_has_unresolved_lease=lambda owner: owner in active,
    )
    cache.claim(runtime_id, envelope, pin_to_owner_leases=True)
    cache.complete(
        runtime_id,
        envelope,
        {
            "ok": True,
            "result": {
                "message": f"tokens {envelope.session_token} {envelope.lease_credentials[0].token}",
                "token": envelope.lease_credentials[0].token,
            },
        },
    )
    immediate = cache.status(runtime_id, envelope.request_id).response
    assert envelope.session_token not in str(immediate)
    assert envelope.lease_credentials[0].token not in str(immediate)

    now[0] = 16.0
    assert cache.prune() == 0
    compacted = cache.status(runtime_id, envelope.request_id)
    assert compacted.status == "completed"
    assert compacted.response["error"]["code"] == "REQUEST_ALREADY_COMPLETED"

    active.clear()
    assert cache.prune() == 1
    assert cache.status(runtime_id, envelope.request_id).status == "unknown"


def test_replay_capacity_never_evicts_pinned_or_in_progress_entries():
    runtime_id = _mcp().runtime_id
    cache = RequestReplayCache(
        max_entries=2,
        owner_has_unresolved_lease=lambda owner: owner == runtime_id,
    )
    first = RequestEnvelope.from_dict(_envelope("A" * 43))
    second = RequestEnvelope.from_dict(_envelope("B" * 43))
    third = RequestEnvelope.from_dict(_envelope("C" * 43))
    cache.claim(runtime_id, first, pin_to_owner_leases=True)
    cache.complete(runtime_id, first, {"ok": True})
    cache.claim(runtime_id, second, pin_to_owner_leases=True)

    with pytest.raises(LeaseProtocolError) as raised:
        cache.claim(runtime_id, third, pin_to_owner_leases=True)
    assert raised.value.code == "REPLAY_JOURNAL_FULL"
    assert cache.status(runtime_id, first.request_id).status == "completed"
    assert cache.status(runtime_id, second.request_id).status == "in_progress"


def test_public_errors_and_redacted_envelopes_do_not_expose_tokens():
    manager, _request_payload, _response, verified = _handshake()
    lease_token = "Z" * 43
    payload = _envelope(verified.session_token)
    payload["lease_credentials"][0]["token"] = lease_token
    payload["params"] = {"auth_secret": "private-value", "safe": "shown"}
    envelope = RequestEnvelope.from_dict(payload)

    rendered = repr(envelope)
    redacted = envelope.redacted_dict()
    assert verified.session_token not in rendered
    assert lease_token not in rendered
    assert "private-value" not in rendered
    assert verified.session_token not in repr(verified)
    assert redacted["session_token"] == "<redacted>"
    assert redacted["lease_credentials"][0]["token"] == "<redacted>"
    assert redacted["params"]["auth_secret"] == "<redacted>"

    error = LeaseProtocolError(
        "TEST_ERROR",
        "Safe failure",
        details={
            "session_token": verified.session_token,
            "nested": {"lease_token": lease_token},
            "token_fingerprint": "sha256:safe",
            "nested_token_digest": "sha256:also-private",
            "secret_fingerprint": "profile-secret-fingerprint",
        },
    )
    public = public_error(error, request_id=envelope.request_id)
    encoded = canonical_json_bytes(public).decode("utf-8")
    assert verified.session_token not in encoded
    assert lease_token not in encoded
    assert public["error"]["details"]["session_token"] == "<redacted>"
    assert public["error"]["details"]["token_fingerprint"] == "<redacted>"
    assert public["error"]["details"]["nested_token_digest"] == "<redacted>"
    assert public["error"]["details"]["secret_fingerprint"] == "<redacted>"

    # Unknown exceptions never expose their text.
    assert "top-secret" not in str(public_error(RuntimeError("top-secret")))
    manager.authenticate_envelope(envelope)


def test_profile_secret_creation_loading_and_no_overwrite(tmp_path):
    path = tmp_path / "profile.auth"
    created = create_profile_secret(path)
    assert len(created) == 32
    assert load_profile_secret(path) == created

    with pytest.raises(LeaseProtocolError) as raised:
        create_profile_secret(path)
    assert raised.value.code == "PROFILE_SECRET_CREATE_FAILED"

    if os.name != "nt":
        path.chmod(0o644)
        with pytest.raises(LeaseProtocolError) as raised:
            load_profile_secret(path)
        assert raised.value.code == "INSECURE_PROFILE_SECRET"


def test_redaction_is_non_mutating():
    source = {"session_token": "secret", "nested": [{"safe": 1}]}
    before = copy.deepcopy(source)
    assert redact_sensitive(source)["session_token"] == "<redacted>"
    assert source == before
