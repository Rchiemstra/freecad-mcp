#!/usr/bin/env python3
"""Honesty checks for setup_isolated_profile FreeCAD binary paths."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
MCP_ROOT = Path(__file__).resolve().parents[2]


def _load_setup():
    path = SCRIPTS / "setup_isolated_profile.py"
    spec = importlib.util.spec_from_file_location(
        "mcp_limits_setup_isolated_profile", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _run_setup(tmp_path, monkeypatch, *, port: str = "19876") -> Path:
    setup = _load_setup()
    monkeypatch.setattr(setup, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "_freecad_mcp_root", lambda: MCP_ROOT)
    monkeypatch.setattr(
        setup,
        "_junction",
        lambda _source, destination: destination.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(setup, "_restrict_owner_only", lambda _path: None)
    monkeypatch.setattr(sys, "argv", ["setup_isolated_profile.py", "--port", port])
    assert setup.main() == 0
    return tmp_path / setup.PROFILE_NAME


def test_setup_leaves_freecadcmd_path_empty_when_binary_missing(
    tmp_path, monkeypatch, capsys
) -> None:
    profile = _run_setup(tmp_path, monkeypatch)
    settings = json.loads(
        (profile / "freecad_mcp_settings.json").read_text(encoding="utf-8")
    )
    assert settings["freecadcmd_path"] == ""

    captured = capsys.readouterr().out
    assert "freecad_exe:" in captured
    assert "FreeCAD.exe" not in captured.split("freecad_exe:", maxsplit=1)[-1]


def test_setup_records_freecadcmd_path_when_binary_exists(
    tmp_path, monkeypatch
) -> None:
    exe = tmp_path / "build" / "release" / "bin" / "FreeCADCmd.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"dummy")

    profile = _run_setup(tmp_path, monkeypatch, port="19879")
    settings = json.loads(
        (profile / "freecad_mcp_settings.json").read_text(encoding="utf-8")
    )
    assert settings["freecadcmd_path"] == str(exe)


def test_setup_records_linux_binaries(tmp_path) -> None:
    setup = _load_setup()
    binary_dir = tmp_path / "build/release/bin"
    binary_dir.mkdir(parents=True)
    for name in ("FreeCAD", "FreeCADCmd"):
        (binary_dir / name).touch()
    assert setup._default_freecadcmd_path(tmp_path) == str(binary_dir / "FreeCADCmd")
    assert setup._default_freecad_exe_path(tmp_path) == str(binary_dir / "FreeCAD")


def test_linux_profile_setup_does_not_mistake_cwd_for_appdata(
    tmp_path, monkeypatch
) -> None:
    setup = _load_setup()
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    user_profile = tmp_path / "data/FreeCAD"
    user_profile.mkdir(parents=True)

    setup._ensure_not_appdata(tmp_path / ".freecad-mcp-isolated")
    assert setup._appdata_freecad() == user_profile
    with pytest.raises(SystemExit, match="Refusing to install"):
        setup._ensure_not_appdata(user_profile / "isolated")
