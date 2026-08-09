"""Unit tests for FreeCADRPC._dispatch document-lock enforcement."""

from __future__ import annotations

import importlib
import inspect
import json
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.document_lock import (
    VERB_CLASSIFICATION,
    acquire_lease,
    ensure_session_id,
    reset_registry_for_tests,
    set_request_identity,
)
from addon.FreeCADMCP.document_lease import (
    DocumentIdentityService,
    DocumentLeaseService,
    LeaseServiceError,
    LeaseOwner,
    SidecarStore,
    sidecar_path_for,
)
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from addon.FreeCADMCP.rpc_server.rpc_server import (
    FreeCADRPC,
    _assert_mutation_file_metadata_unchanged,
    _generated_execute_signature as addon_generated_execute_signature,
)
from freecad_mcp.freecad_client import (
    _generated_execute_signature as client_generated_execute_signature,
)


@pytest.fixture(autouse=True)
def _clean():
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


def _install_foreign_v2_sidecar(tmp_path, monkeypatch):
    model = tmp_path / "Locked.FCStd"
    model.write_bytes(b"FCStd test payload")
    locked = SimpleNamespace(
        Name="Locked",
        Label="Locked",
        FileName=str(model),
        Modified=False,
    )
    unlocked = SimpleNamespace(
        Name="Unlocked",
        Label="Unlocked",
        FileName="",
        Modified=False,
    )
    documents = {locked.Name: locked, unlocked.Name: unlocked}
    monkeypatch.setattr(addon_rpc.FreeCAD, "getDocument", documents.get)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "listDocuments", lambda: dict(documents)
    )
    monkeypatch.setattr(addon_rpc.FreeCAD, "ActiveDocument", locked)

    identities = DocumentIdentityService()
    identity = identities.register_document(locked)
    owner = LeaseOwner(
        addon_profile_id=str(uuid.uuid4()),
        addon_runtime_id=str(uuid.uuid4()),
        freecad_pid=10,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="test-boot",
        mcp_instance_id=str(uuid.uuid4()),
        mcp_pid=20,
        mcp_process_started_at="2026-07-22T00:00:01Z",
        hostname="test-host",
        client="foreign-test",
        agent_id="agent-a",
    )
    service = DocumentLeaseService(
        identities,
        SidecarStore(network_detector=lambda _path: False),
    )
    service.acquire(
        identity.session_uuid,
        owner,
        snapshot_id=str(uuid.uuid4()),
    )
    # The dispatching addon has no matching in-memory authority/credential, so
    # the valid persisted record is deliberately foreign to this request.
    monkeypatch.setattr(addon_rpc, "document_lease_service", None)
    return locked, unlocked, sidecar_path_for(model)


@pytest.mark.unit
def test_open_document_rejects_duplicate_before_calling_freecad(monkeypatch):
    from addon.FreeCADMCP.rpc_server import gui_tools

    identity_service = SimpleNamespace(
        assert_open_path_available=MagicMock(
            side_effect=RuntimeError("same filesystem file is already open")
        )
    )
    opener = MagicMock(side_effect=AssertionError("FreeCAD.openDocument was called"))
    monkeypatch.setattr(addon_rpc, "document_identity_service", identity_service)
    monkeypatch.setattr(gui_tools, "open_document", opener)
    rpc = FreeCADRPC()
    monkeypatch.setattr(rpc, "_dispatch_gui", lambda task: task())

    result = rpc.open_document("C:/models/duplicate.FCStd")

    assert result["ok"] is False
    assert result["error_code"] == "DUPLICATE_OR_INVALID_DOCUMENT_OPEN"
    identity_service.assert_open_path_available.assert_called_once()
    opener.assert_not_called()


@pytest.mark.unit
class TestRpcLockEnforcement:
    def test_lease_service_errors_deep_redact_credentials_and_fingerprints(self):
        exc = LeaseServiceError(
            "safe failure",
            details={
                "token": "raw-token",
                "nested": {
                    "session_token": "rpc-session",
                    "token_fingerprint": "sha256:private",
                },
            },
        )

        result = addon_rpc._lease_service_error(exc)

        assert result["details"]["token"] == "<redacted>"
        assert result["details"]["nested"]["session_token"] == "<redacted>"
        assert result["details"]["nested"]["token_fingerprint"] == "<redacted>"

    def test_mutation_preflight_rejects_external_file_change(self, tmp_path):
        model = tmp_path / "model.FCStd"
        model.write_bytes(b"baseline")
        stat_result = model.stat()
        record = SimpleNamespace(
            document=SimpleNamespace(canonical_path=str(model)),
            baseline=SimpleNamespace(
                size=stat_result.st_size,
                mtime_ns=stat_result.st_mtime_ns,
            ),
        )

        _assert_mutation_file_metadata_unchanged(record)
        model.write_bytes(b"externally changed")

        with pytest.raises(RuntimeError, match="changed externally"):
            _assert_mutation_file_metadata_unchanged(record)

    def test_generated_operation_signature_contract_matches_client(self):
        options = {
            "document": "Doc",
            "affected_documents": ["Other", "Doc"],
            "operation_id": "partdesign.create-pad",
        }
        expected = client_generated_execute_signature(
            session_token="session-secret",
            request_id="request-id",
            code="mutate()",
            options=options,
        )
        actual = addon_generated_execute_signature(
            session_token="session-secret",
            request_id="request-id",
            code="mutate()",
            options=options,
        )

        assert actual == expected
        assert actual != addon_generated_execute_signature(
            session_token="session-secret",
            request_id="another-request",
            code="mutate()",
            options=options,
        )

    def test_every_public_rpc_method_has_an_explicit_descriptor_source(self):
        public_methods = {
            name
            for name, member in inspect.getmembers(FreeCADRPC, inspect.isfunction)
            if not name.startswith("_")
        }
        assert public_methods == set(VERB_CLASSIFICATION)

    def test_remote_force_release_is_a_local_recovery_tombstone(self):
        result = FreeCADRPC().force_release_stale_lock("C:/model.FCStd")
        assert result["success"] is False
        assert result["error_code"] == "LOCAL_RECOVERY_REQUIRED"

    def test_freecad_first_import_publishes_package_alias(self):
        """The import order used by FreeCAD must also converge on one module."""
        repository = Path(__file__).resolve().parents[1]
        addon_dir = repository / "addon" / "FreeCADMCP"
        script = (
            "import importlib, sys; "
            f"sys.path.insert(0, {str(addon_dir)!r}); "
            "freecad_mod = importlib.import_module('document_lock'); "
            "package_mod = importlib.import_module('addon.FreeCADMCP.document_lock'); "
            "assert freecad_mod is package_mod; "
            "assert sys.modules['document_lock'] is "
            "sys.modules['addon.FreeCADMCP.document_lock']"
        )
        subprocess.run(
            [sys.executable, "-c", script],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_freecad_and_package_imports_share_lock_state(
        self, tmp_path, monkeypatch
    ):
        """FreeCAD's top-level import must not create a second lock service."""
        addon_dir = (
            Path(__file__).resolve().parents[1]
            / "addon"
            / "FreeCADMCP"
        )
        monkeypatch.syspath_prepend(str(addon_dir))

        package_module = importlib.import_module("addon.FreeCADMCP.document_lock")
        freecad_module = importlib.import_module("document_lock")

        assert package_module is freecad_module
        assert sys.modules["addon.FreeCADMCP.document_lock"] is freecad_module

        _enable(tmp_path, monkeypatch)
        assert freecad_module.is_enforcement_enabled() is True

        key = package_module.ensure_session_id("SharedDoc")
        acquired = freecad_module.acquire_lease(
            doc_key=key,
            doc_name="SharedDoc",
            instance_id="shared-agent",
            pid=1,
        )
        package_module.set_request_identity(
            instance_id="shared-agent", lease_token=acquired["token"]
        )
        assert freecad_module.get_request_identity()["instance_id"] == "shared-agent"
        assert package_module.check_mutation_allowed(key)["success"] is True

    def test_flag_off_passthrough(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch, enable=False, enforce=False)
        rpc = FreeCADRPC()
        rpc.ping = MagicMock(return_value=True)
        # Re-bind ping on instance — _dispatch uses getattr(self, method)
        assert rpc._dispatch("ping", ()) is True

    def test_observe_live_execute_requires_affected_documents_with_foreign_sidecar(
        self, tmp_path, monkeypatch
    ):
        _enable(tmp_path, monkeypatch, enable=True, enforce=False)
        _locked, _unlocked, _sidecar = _install_foreign_v2_sidecar(
            tmp_path, monkeypatch
        )
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True})

        for affected in (None, [], [""]):
            options = {"document": "Unlocked", "read_only": False}
            if affected is not None:
                options["affected_documents"] = affected
            result = rpc._dispatch(
                "execute_code",
                (
                    "FreeCAD.ActiveDocument.addObject('Part::Feature', 'Bypass')",
                    options,
                ),
            )

            assert result["success"] is False
            assert result["error_code"] == "FOREIGN_LEASE_SCOPE_REQUIRED"
            assert result["blocked_documents"] == [
                {
                    "document_name": "Locked",
                    "error_code": "DOCUMENT_LEASE_CONFLICT",
                }
            ]
        rpc.execute_code.assert_not_called()

    def test_observe_explicit_unlocked_scope_remains_available(
        self, tmp_path, monkeypatch
    ):
        _enable(tmp_path, monkeypatch, enable=True, enforce=False)
        _locked, _unlocked, _sidecar = _install_foreign_v2_sidecar(
            tmp_path, monkeypatch
        )
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True})
        options = {
            "document": "Unlocked",
            "affected_documents": ["Unlocked"],
            "read_only": False,
        }

        result = rpc._dispatch(
            "execute_code",
            ("FreeCAD.getDocument('Unlocked').recompute()", options),
        )

        assert result == {"success": True}
        rpc.execute_code.assert_called_once_with(
            "FreeCAD.getDocument('Unlocked').recompute()", options
        )

    def test_observe_unresolved_typed_mutation_is_blocked_by_foreign_sidecar(
        self, tmp_path, monkeypatch
    ):
        _enable(tmp_path, monkeypatch, enable=True, enforce=False)
        _locked, _unlocked, _sidecar = _install_foreign_v2_sidecar(
            tmp_path, monkeypatch
        )
        rpc = FreeCADRPC()
        rpc.create_object = MagicMock(return_value={"success": True})

        result = rpc._dispatch(
            "create_object",
            ("Missing", {"Type": "Part::Feature", "Name": "Bypass"}),
        )

        assert result["success"] is False
        assert result["error_code"] == "FOREIGN_LEASE_SCOPE_UNRESOLVED"
        rpc.create_object.assert_not_called()

    def test_observe_unresolved_mutation_fails_closed_on_unknown_sidecar(
        self, tmp_path, monkeypatch
    ):
        _enable(tmp_path, monkeypatch, enable=True, enforce=False)
        _locked, _unlocked, sidecar = _install_foreign_v2_sidecar(
            tmp_path, monkeypatch
        )
        sidecar.write_text("{malformed", encoding="utf-8")
        rpc = FreeCADRPC()
        rpc.create_object = MagicMock(return_value={"success": True})

        result = rpc._dispatch(
            "create_object",
            ("Missing", {"Type": "Part::Feature", "Name": "Bypass"}),
        )

        assert result["success"] is False
        assert result["error_code"] == "FOREIGN_LEASE_SCOPE_UNRESOLVED"
        assert result["blocked_documents"][0]["error_code"] == "SIDECAR_UNKNOWN"
        rpc.create_object.assert_not_called()

    def test_v1_unowned_mutation_requires_protocol_v2(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        rpc = FreeCADRPC()
        rpc.pad_feature = MagicMock(return_value={"success": True})
        set_request_identity(instance_id="me")
        # Ensure session id exists so resolve works without FreeCAD file
        ensure_session_id("Doc")
        result = rpc._dispatch(
            "pad_feature",
            ("Doc", "Sketch", "Pad", 10.0, None, False, False),
        )
        assert isinstance(result, dict)
        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        rpc.pad_feature.assert_not_called()

    def test_v1_owned_mutation_still_requires_protocol_v2(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = ensure_session_id("Doc")
        acquire_lease(doc_key=key, doc_name="Doc", instance_id="me", pid=1)
        set_request_identity(instance_id="me")

        rpc = FreeCADRPC()
        rpc.pad_feature = MagicMock(return_value={"success": True, "name": "Pad"})
        # resolve_doc_key will try FreeCAD.getDocument — stub it
        with patch(
            "addon.FreeCADMCP.document_lock.resolve_doc_key",
            return_value=key,
        ):
            result = rpc._dispatch(
                "pad_feature",
                ("Doc", "Sketch", "Pad", 10.0, None, False, False),
            )
        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        rpc.pad_feature.assert_not_called()

    @pytest.mark.parametrize(
        "method,params",
        [
            ("acquire_document_lock", ("Doc",)),
            ("update_document_lock", ({"document_name": "Doc"},)),
            ("release_document_lock", ("legacy-key", "legacy-token")),
            ("save_document", ({"document_name": "Doc"},)),
            ("save_document_as", ({"document_name": "Doc"}, "C:/next.FCStd")),
            ("finalize_document_edit", ({"document_name": "Doc"},)),
        ],
    )
    def test_v1_lease_lifecycle_calls_require_protocol_v2_in_enforce_mode(
        self, tmp_path, monkeypatch, method, params
    ):
        _enable(tmp_path, monkeypatch)
        set_request_identity(instance_id="legacy-runtime")
        rpc = FreeCADRPC()
        target = MagicMock(return_value={"success": True})
        setattr(rpc, method, target)

        result = rpc._dispatch(method, params)

        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        target.assert_not_called()

    def test_other_instance_refused(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = ensure_session_id("Doc")
        acquire_lease(doc_key=key, doc_name="Doc", instance_id="other", pid=1)
        set_request_identity(instance_id="me")

        rpc = FreeCADRPC()
        rpc.pad_feature = MagicMock(return_value={"success": True})
        with patch(
            "addon.FreeCADMCP.document_lock.resolve_doc_key",
            return_value=key,
        ):
            result = rpc._dispatch(
                "pad_feature",
                ("Doc", "Sketch", "Pad", 10.0, None, False, False),
            )
        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        rpc.pad_feature.assert_not_called()

    def test_execute_code_requires_document(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        set_request_identity(instance_id="me")
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True})
        result = rpc._dispatch(
            "execute_code",
            ("doc.addObject('Part::Box','Box')", {"read_only": False}),
        )
        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        rpc.execute_code.assert_not_called()

    def test_execute_code_multi_doc_rejection(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        key = ensure_session_id("DocA")
        acquire_lease(doc_key=key, doc_name="DocA", instance_id="me", pid=1)
        set_request_identity(instance_id="me")

        code = (
            "a = FreeCAD.getDocument('DocA')\n"
            "b = FreeCAD.getDocument('DocB')\n"
        )
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True})
        with patch(
            "addon.FreeCADMCP.document_lock.resolve_doc_key",
            side_effect=lambda **kw: ensure_session_id(kw["doc_name"]),
        ):
            result = rpc._dispatch(
                "execute_code",
                (code, {"document": "DocA", "read_only": False}),
            )
        assert result.get("error_code") == "LEASE_PROTOCOL_REQUIRED"
        rpc.execute_code.assert_not_called()

    def test_execute_code_read_only_no_lease(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        set_request_identity(instance_id="me")
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True, "output": "ok"})
        result = rpc._dispatch(
            "execute_code",
            (
                "print(1)",
                {
                    "document": "Doc",
                    "read_only": True,
                    "execution_mode": "gui",
                },
            ),
        )
        assert result.get("success") is True
        rpc.execute_code.assert_called_once()
        assert rpc.execute_code.call_args.args[1]["execution_mode"] == "worker"
