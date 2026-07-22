"""Unit tests for FreeCADRPC._dispatch document-lock enforcement."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.document_lock import (
    acquire_lease,
    ensure_session_id,
    reset_registry_for_tests,
    set_request_identity,
)
from addon.FreeCADMCP.rpc_server.rpc_server import FreeCADRPC


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


@pytest.mark.unit
class TestRpcLockEnforcement:
    def test_flag_off_passthrough(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch, enable=False, enforce=False)
        rpc = FreeCADRPC()
        rpc.ping = MagicMock(return_value=True)
        # Re-bind ping on instance — _dispatch uses getattr(self, method)
        assert rpc._dispatch("ping", ()) is True

    def test_unowned_mutation_refused(self, tmp_path, monkeypatch):
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
        assert result.get("error_code") == "document_not_locked"
        rpc.pad_feature.assert_not_called()

    def test_owned_mutation_allowed(self, tmp_path, monkeypatch):
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
        assert result == {"success": True, "name": "Pad"}
        rpc.pad_feature.assert_called_once()

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
        assert result.get("error_code") == "document_locked_by_other"
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
        assert result.get("error_code") == "document_not_locked"
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
        assert result.get("error_code") == "multi_document_undeclared"
        assert "DocB" in result.get("undeclared", [])
        rpc.execute_code.assert_not_called()

    def test_execute_code_read_only_no_lease(self, tmp_path, monkeypatch):
        _enable(tmp_path, monkeypatch)
        set_request_identity(instance_id="me")
        rpc = FreeCADRPC()
        rpc.execute_code = MagicMock(return_value={"success": True, "output": "ok"})
        result = rpc._dispatch(
            "execute_code",
            ("print(1)", {"document": "Doc", "read_only": True}),
        )
        assert result.get("success") is True
        rpc.execute_code.assert_called_once()
