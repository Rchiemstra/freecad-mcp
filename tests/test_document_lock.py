"""Unit tests for per-document MCP write leases."""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from addon.FreeCADMCP.document_lock import (
    LEASE_TTL_SECONDS,
    LeaseRecord,
    VERB_CLASSIFICATION,
    VerbKind,
    _public_sidecar_payload,
    acquire_lease,
    check_mutation_allowed,
    classify_verb,
    configure_runtime_lease_mode,
    force_release_stale_lock,
    heartbeat_lease,
    is_enabled,
    is_enforcement_enabled,
    migrate_lease_key,
    release_lease,
    reset_registry_for_tests,
    set_request_identity,
    sidecar_path_for,
    validate_unsafe_execute_scope,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def _enable(tmp_path, monkeypatch, *, enable=True, enforce=True):
    settings = tmp_path / "freecad_mcp_settings.json"
    settings.write_text(
        json.dumps(
            {
                "enable_document_lock": enable,
                "document_lock_enforcement": enforce,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.document_lock._settings_path",
        lambda: settings,
    )
    return settings


@pytest.mark.unit
class TestDocumentLockSettings:
    def test_missing_settings_file_uses_new_profile_observe_default(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(
            "addon.FreeCADMCP.document_lock._settings_path",
            lambda: tmp_path / "missing-settings.json",
        )
        assert is_enabled()
        assert not is_enforcement_enabled()

    def test_disabled_by_default(self, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "addon.FreeCADMCP.document_lock._settings_path",
            lambda: settings,
        )
        assert not is_enabled()
        assert not is_enforcement_enabled()

    def test_enable_without_enforcement(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch, enable=True, enforce=False)
        assert is_enabled()
        assert not is_enforcement_enabled()

    def test_enforcement_requires_enable(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch, enable=False, enforce=True)
        assert not is_enforcement_enabled()

    def test_runtime_mode_is_latched_against_live_settings_downgrade(
        self, tmp_path, monkeypatch
    ):
        settings = _enable(tmp_path, monkeypatch, enable=True, enforce=True)
        configure_runtime_lease_mode("enforce")
        settings.write_text(
            json.dumps({"document_lease_mode": "off"}), encoding="utf-8"
        )
        assert is_enabled()
        assert is_enforcement_enabled()

        settings.unlink()
        assert is_enabled()
        assert is_enforcement_enabled()

    def test_malformed_settings_fail_closed_before_runtime_latch(
        self, tmp_path, monkeypatch
    ):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text("{broken", encoding="utf-8")
        monkeypatch.setattr(
            "addon.FreeCADMCP.document_lock._settings_path",
            lambda: settings,
        )
        assert is_enabled()
        assert is_enforcement_enabled()

    @pytest.mark.parametrize(
        ("mode", "enabled", "enforced"),
        [
            ("off", False, False),
            ("observe", True, False),
            ("enforce", True, True),
        ],
    )
    def test_explicit_lease_mode_is_authoritative(
        self, tmp_path, monkeypatch, mode, enabled, enforced
    ):
        settings = _enable(tmp_path, monkeypatch, enable=False, enforce=False)
        settings.write_text(
            json.dumps(
                {
                    "document_lease_mode": mode,
                    # Deliberately contradictory legacy keys prove that new
                    # configuration cannot silently fall back to v1 policy.
                    "enable_document_lock": mode == "off",
                    "document_lock_enforcement": mode != "enforce",
                }
            ),
            encoding="utf-8",
        )
        assert is_enabled() is enabled
        assert is_enforcement_enabled() is enforced


@pytest.mark.unit
class TestUnsafeExecuteScope:
    def test_literal_declared_document_is_accepted(self):
        result = validate_unsafe_execute_scope(
            "FreeCAD.getDocument('Doc').recompute()", {"Doc"}
        )
        assert result == {
            "ok": True,
            "referenced_documents": ["Doc"],
            "violations": [],
        }

    @pytest.mark.parametrize(
        "code, marker",
        [
            ("import FreeCAD", "imports_not_allowed"),
            ("exec(payload)", "dynamic_code_or_lookup_not_allowed:exec"),
            ("FreeCAD.getDocument(name)", "dynamic_document_lookup_not_allowed"),
            ("FreeCAD.ActiveDocument.recompute()", "active_document_not_allowed"),
            ("FreeCAD.newDocument('Other')", "document_lifecycle_not_allowed"),
            ("FreeCAD.getDocument('Other')", "undeclared_documents:Other"),
        ],
    )
    def test_ambiguous_or_lifecycle_code_is_rejected(self, code, marker):
        result = validate_unsafe_execute_scope(code, {"Doc"})
        assert result["ok"] is False
        assert any(marker in item for item in result["violations"])


@pytest.mark.unit
class TestDocumentLockSidecar:
    def test_legacy_record_repr_never_exposes_token(self):
        token = "legacy-bearer-token-must-not-appear"
        record = LeaseRecord(
            doc_key="document-key",
            doc_name="Document",
            token=token,
            instance_id="instance",
            client="codex",
            pid=42,
            host="localhost",
        )

        assert token not in repr(record)
        assert "token=" not in repr(record)

    def test_malformed_sidecar_diagnostic_recursively_redacts_secrets(self):
        lease_token = "nested-lease-token-must-not-appear"
        session_token = "nested-session-token-must-not-appear"
        fingerprint = "sha256:nested-fingerprint-must-not-appear"
        wrapped_secret = "wrapped-secret-must-not-appear"
        malformed = {
            "schema_version": "not-an-integer",
            "document": {"name": "UsefulDocumentName"},
            "owner": {
                "client": "codex",
                "session_token": session_token,
            },
            "credential": {
                "lease_id": "useful-lease-id",
                "token": lease_token,
            },
            "token_fingerprint": fingerprint,
            "auth_secret": {"current": wrapped_secret},
            "error": {
                "code": "MALFORMED_TEST_RECORD",
                "message": (
                    f"coordination failed for {lease_token}; session="
                    f"{session_token}; fingerprint={fingerprint}; wrapped="
                    f"{wrapped_secret}"
                ),
            },
        }

        public = _public_sidecar_payload(malformed)
        rendered = json.dumps(public, sort_keys=True)

        assert lease_token not in rendered
        assert session_token not in rendered
        assert fingerprint not in rendered
        assert wrapped_secret not in rendered
        assert public["document"]["name"] == "UsefulDocumentName"
        assert public["owner"]["client"] == "codex"
        assert public["credential"]["lease_id"] == "useful-lease-id"
        assert public["error"]["code"] == "MALFORMED_TEST_RECORD"
        assert "[REDACTED]" in public["error"]["message"]

    def test_atomic_exclusive_create(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_bytes(b"PK\x03\x04")
        key = str(fcstd.resolve())

        first = acquire_lease(
            doc_key=key,
            doc_name="model",
            instance_id="inst-a",
            client="agent-a",
            pid=111,
            host="localhost",
        )
        assert first["success"] is True
        assert sidecar_path_for(key).is_file()

        second = acquire_lease(
            doc_key=key,
            doc_name="model",
            instance_id="inst-b",
            client="agent-b",
            pid=222,
            host="localhost",
        )
        assert second["success"] is False
        assert second["error_code"] == "document_locked_by_other"

    def test_metadata_round_trip(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        fcstd = tmp_path / "part.FCStd"
        fcstd.write_bytes(b"data")
        key = str(fcstd.resolve())
        result = acquire_lease(
            doc_key=key,
            doc_name="part",
            instance_id="inst-a",
            client="cursor",
            pid=42,
            host="host1",
            task_description="pad spool",
        )
        lease = result["lease"]
        assert lease["instance_id"] == "inst-a"
        assert lease["client"] == "cursor"
        assert lease["pid"] == 42
        assert lease["task_description"] == "pad spool"
        assert "token" not in lease
        assert "token_fingerprint" not in lease
        assert lease["baseline_hash"]

        side = json.loads(sidecar_path_for(key).read_text(encoding="utf-8"))
        assert "token" not in side
        assert side["token_fingerprint"].startswith("sha256:")
        assert side["instance_id"] == "inst-a"

    def test_heartbeat_renew(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_bytes(b"x")
        key = str(fcstd.resolve())
        acq = acquire_lease(doc_key=key, doc_name="model", instance_id="a", pid=1)
        token = acq["token"]
        before = acq["lease"]["last_heartbeat"]
        time.sleep(0.02)
        hb = heartbeat_lease(key, token, current_operation="Pad:Spool")
        assert hb["success"] is True
        assert hb["lease"]["last_heartbeat"] >= before
        assert hb["lease"]["current_operation"] == "Pad:Spool"

        refused = heartbeat_lease(key, token, state="LOCKED_EDITING")
        assert refused["success"] is False
        assert refused["error_code"] == "state_owned_by_server"

    def test_clean_release_removes_sidecar(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_bytes(b"x")
        key = str(fcstd.resolve())
        acq = acquire_lease(doc_key=key, doc_name="model", instance_id="a", pid=1)
        side = sidecar_path_for(key)
        assert side.is_file()
        rel = release_lease(key, acq["token"])
        assert rel["success"] is True
        assert not side.exists()

    def test_force_release_stale_requires_dead_pid(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_bytes(b"x")
        key = str(fcstd.resolve())
        acq = acquire_lease(doc_key=key, doc_name="model", instance_id="a", pid=999001)
        token = acq["token"]

        # Not stale yet
        refused = force_release_stale_lock(key)
        assert refused["error_code"] == "lock_not_stale"

        # Expire heartbeat but owner still alive
        with patch(
            "addon.FreeCADMCP.document_lock.time.time",
            return_value=time.time() + LEASE_TTL_SECONDS + 10,
        ):
            with patch(
                "addon.FreeCADMCP.document_lock.pid_alive", return_value=True
            ):
                alive = force_release_stale_lock(key)
        assert alive["error_code"] == "owner_still_alive"
        assert sidecar_path_for(key).is_file()

        # Expire + dead pid → release
        with patch(
            "addon.FreeCADMCP.document_lock.time.time",
            return_value=time.time() + LEASE_TTL_SECONDS + 10,
        ):
            with patch(
                "addon.FreeCADMCP.document_lock.pid_alive", return_value=False
            ):
                # Refresh registry heartbeat artificially by re-reading
                # force_release uses sidecar/registry last_heartbeat from acquire
                # which is old relative to patched time — good.
                ok = force_release_stale_lock(key)
        assert ok["success"] is True
        assert not sidecar_path_for(key).exists()
        # token unused but kept for clarity
        assert token

    def test_uuid_to_path_migration(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        session = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        acq = acquire_lease(
            doc_key=session,
            doc_name="Unsaved",
            instance_id="inst-a",
            pid=1,
        )
        assert acq["success"] is True
        token = acq["token"]

        dest = tmp_path / "saved.FCStd"
        dest.write_bytes(b"PK")
        dest_key = str(dest.resolve())

        # Destination sidecar must appear before old key is cleared
        migrated = migrate_lease_key(session, dest_key, doc_name="Unsaved")
        assert migrated["success"] is True
        assert "token" not in migrated["lease"]
        assert migrated["lease"]["doc_key"] == dest_key
        assert sidecar_path_for(dest_key).is_file()
        # Old UUID key has no sidecar; registry moved
        from addon.FreeCADMCP.document_lock import get_lease

        assert get_lease(session) is None
        assert get_lease(dest_key) is not None
        assert get_lease(dest_key).token == token


@pytest.mark.unit
class TestMutationGate:
    def test_owned_allowed(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        acquired = acquire_lease(
            doc_key=key, doc_name="Doc", instance_id="me", pid=1
        )
        set_request_identity(instance_id="me", lease_token=acquired["token"])
        assert check_mutation_allowed(key)["success"] is True

    def test_owned_without_token_is_refused(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        acquire_lease(doc_key=key, doc_name="Doc", instance_id="me", pid=1)
        set_request_identity(instance_id="me", lease_token=None)
        result = check_mutation_allowed(key)
        assert result["success"] is False
        assert result["error_code"] == "missing_lease_token"

    def test_unowned_document_not_locked(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        set_request_identity(instance_id="me")
        result = check_mutation_allowed("missing-key")
        assert result["error_code"] == "document_not_locked"

    def test_other_instance(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        acquire_lease(doc_key=key, doc_name="Doc", instance_id="other", pid=1)
        set_request_identity(instance_id="me")
        result = check_mutation_allowed(key)
        assert result["error_code"] == "document_locked_by_other"


@pytest.mark.unit
class TestVerbClassification:
    def test_every_freecadrpc_verb_classified(self):
        rpc_path = (
            Path(__file__).resolve().parents[1]
            / "addon"
            / "FreeCADMCP"
            / "rpc_server"
            / "rpc_server.py"
        )
        source = rpc_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        verbs: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "FreeCADRPC":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        verbs.add(item.name)
        missing = sorted(verbs - set(VERB_CLASSIFICATION))
        assert not missing, f"Unclassified FreeCADRPC verbs (fail-closed risk): {missing}"

    def test_unknown_verb_is_mutating(self):
        kind, _ = classify_verb("brand_new_mutating_tool")
        assert kind is VerbKind.MUTATING
