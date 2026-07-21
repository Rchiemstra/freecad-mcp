#!/usr/bin/env python3
"""Create an isolated FreeCAD user profile for freecad-isolated MCP.

Creates ``<repo>/.freecad-mcp-isolated/{Mod,temp}``, junctions the addon into
``Mod/FreeCADMCP``, and writes ``freecad_mcp_settings.json`` with rpc_port 9876.

Refuses to write under ``%APPDATA%\\FreeCAD`` so the existing MCP profile stays
untouched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ISOLATED_PORT = 9876
PROFILE_NAME = ".freecad-mcp-isolated"


def _repo_root() -> Path:
    # scripts/ -> freecad-mcp/ -> mcp/ -> tools/ -> FreeCAD repo
    return Path(__file__).resolve().parents[4]


def _freecad_mcp_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _appdata_freecad() -> Path:
    appdata = os.environ.get("APPDATA") or ""
    return Path(appdata) / "FreeCAD" if appdata else Path()


def _ensure_not_appdata(path: Path) -> None:
    app = _appdata_freecad()
    if not app or not app.exists():
        return
    try:
        path.resolve().relative_to(app.resolve())
    except ValueError:
        return
    raise SystemExit(
        f"Refusing to install isolated profile under AppData FreeCAD: {path}"
    )


def _junction(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        if dst.is_dir() and not dst.is_symlink():
            # Existing real directory — remove only if empty-ish junction target
            pass
        # Remove previous junction/symlink/dir carefully
        if sys.platform == "win32":
            # rmdir removes junctions without deleting target contents
            subprocess.run(["cmd", "/c", "rmdir", str(dst)], check=False)
            if dst.exists():
                import shutil

                shutil.rmtree(dst)
        else:
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                import shutil

                shutil.rmtree(dst)

    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        # Directory junction (no admin required)
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise SystemExit(
                f"Failed to create junction {dst} -> {src}:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
    else:
        dst.symlink_to(src, target_is_directory=True)


def main() -> int:
    repo = _repo_root()
    mcp_root = _freecad_mcp_root()
    addon_src = mcp_root / "addon" / "FreeCADMCP"
    if not addon_src.is_dir():
        raise SystemExit(f"Addon source not found: {addon_src}")

    profile = repo / PROFILE_NAME
    _ensure_not_appdata(profile)

    mod_dir = profile / "Mod"
    temp_dir = profile / "temp"
    mod_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    addon_dst = mod_dir / "FreeCADMCP"
    _junction(addon_src, addon_dst)

    settings = {
        "remote_enabled": False,
        "allowed_ips": "127.0.0.1",
        "auto_start_rpc": True,
        "rpc_port": ISOLATED_PORT,
        "freecadcmd_path": str(repo / "build" / "release" / "bin" / "FreeCADCmd.exe"),
        "allow_remote_execute_code": False,
    }
    settings_path = profile / "freecad_mcp_settings.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    report = {
        "profile": str(profile),
        "mod": str(mod_dir),
        "addon": str(addon_dst),
        "addon_source": str(addon_src),
        "settings": str(settings_path),
        "rpc_port": ISOLATED_PORT,
        "freecad_exe": str(repo / "build" / "release" / "bin" / "FreeCAD.exe"),
    }
    print("Isolated FreeCAD MCP profile ready:")
    for key, value in report.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
