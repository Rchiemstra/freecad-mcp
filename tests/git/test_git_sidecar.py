"""Tests for MCP Git sidecar adapter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from addon.FreeCADMCP.git_sidecar import (
    _find_freecad_git,
    _is_eligible_target,
    export_sidecar_after_save,
    is_enabled,
)


@pytest.mark.unit
class TestMcpGitSidecar:
    def test_export_command_uses_prefix_python(self, tmp_path, monkeypatch):
        if sys.platform == "win32":
            python = tmp_path / "python.exe"
        else:
            python = tmp_path / "bin" / "python"
            python.parent.mkdir()
        python.touch()
        monkeypatch.setattr("addon.FreeCADMCP.git_sidecar.sys.prefix", str(tmp_path))

        assert _find_freecad_git() == [
            str(python),
            "-m",
            "freecad_git.cli",
            "export",
        ]

    def test_ineligible_snapshot_path(self):
        assert not _is_eligible_target("/tmp/mcp_snap_abc.FCStd")

    def test_eligible_fcstd(self):
        assert _is_eligible_target("/models/part.FCStd")

    def test_disabled_by_default(self, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text(json.dumps({"remote_enabled": False}), encoding="utf-8")
        monkeypatch.setattr(
            "addon.FreeCADMCP.git_sidecar._settings_path",
            lambda: settings,
        )
        assert not is_enabled()

    def test_enabled_when_configured(self, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text(
            json.dumps({"generate_git_sidecar_after_save": True}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "addon.FreeCADMCP.git_sidecar._settings_path",
            lambda: settings,
        )
        assert is_enabled()

    def test_export_skipped_when_disabled(self, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(
            "addon.FreeCADMCP.git_sidecar._settings_path",
            lambda: settings,
        )
        result = export_sidecar_after_save(str(tmp_path / "model.FCStd"))
        assert result["skipped"] is True

    @patch("addon.FreeCADMCP.git_sidecar.subprocess.run")
    def test_export_success(self, mock_run, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text(
            json.dumps({"generate_git_sidecar_after_save": True}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "addon.FreeCADMCP.git_sidecar._settings_path",
            lambda: settings,
        )
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_bytes(b"PK\x03\x04")  # not real, export may fail in integration
        sidecar = tmp_path / "model.FCStd.git.json"
        sidecar.write_text("{}", encoding="utf-8")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = export_sidecar_after_save(str(fcstd))
        assert result["ok"] is True
        assert result["sidecar"] == str(sidecar)
        expected_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        assert mock_run.call_args.kwargs["creationflags"] == expected_flags

    @patch("addon.FreeCADMCP.git_sidecar.subprocess.run")
    def test_export_failure_reported(self, mock_run, tmp_path, monkeypatch):
        settings = tmp_path / "freecad_mcp_settings.json"
        settings.write_text(
            json.dumps({"generate_git_sidecar_after_save": True}),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "addon.FreeCADMCP.git_sidecar._settings_path",
            lambda: settings,
        )
        fcstd = tmp_path / "model.FCStd"
        fcstd.write_text("", encoding="utf-8")
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="unsafe archive")
        result = export_sidecar_after_save(str(fcstd))
        assert result["ok"] is False
        assert "unsafe archive" in result["error"]
