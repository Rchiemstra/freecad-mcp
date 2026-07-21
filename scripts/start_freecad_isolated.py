#!/usr/bin/env python3
"""Launch build/release FreeCAD with the isolated MCP user profile.

Sets FREECAD_USER_HOME / FREECAD_USER_DATA / FREECAD_USER_TEMP to
``<repo>/.freecad-mcp-isolated`` and starts ``build/release/bin/FreeCAD.exe``
with the same pixi/Qt PATH setup as the parent ``start_freecad.py``.

Does not call parent ``start_freecad.main`` (that installs into AppData and
waits on :9875). Does not touch the existing default MCP session.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import xmlrpc.client
from pathlib import Path


PROFILE_NAME = ".freecad-mcp-isolated"
ISOLATED_PORT = 9876


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _profile_rpc_port(profile: Path) -> int:
    """Read rpc_port from the isolated profile settings (stays in sync with
    whatever setup_isolated_profile.py wrote); falls back to ISOLATED_PORT."""
    settings_path = profile / "freecad_mcp_settings.json"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return int(data.get("rpc_port", ISOLATED_PORT))
    except Exception:
        return ISOLATED_PORT


def _load_parent_start_freecad():
    """Load FreeCADModeling/start_freecad.py for PATH/Qt helpers only."""
    parent = _repo_root().parent / "start_freecad.py"
    if not parent.is_file():
        # Fallback: sibling naming if repo is checked out alone
        alt = _repo_root() / ".." / "start_freecad.py"
        parent = alt.resolve() if alt.is_file() else parent
    if not parent.is_file():
        raise SystemExit(f"Parent start_freecad.py not found at {parent}")
    spec = importlib.util.spec_from_file_location("freecadmodeling_start_freecad", parent)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {parent}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    repo = _repo_root()
    profile = repo / PROFILE_NAME
    freecad = repo / "build" / "release" / "bin" / "FreeCAD.exe"

    if not freecad.is_file():
        raise SystemExit(f"build/release FreeCAD not found: {freecad}")
    if not profile.is_dir():
        raise SystemExit(
            f"Isolated profile missing: {profile}\n"
            "Run scripts/setup_isolated_profile.py first."
        )
    for required in (profile / "Mod", profile / "temp"):
        required.mkdir(parents=True, exist_ok=True)

    isolated_port = _profile_rpc_port(profile)

    helper = _load_parent_start_freecad()
    cmd, cwd, env = helper._launch_details(freecad, sys.argv[1:])

    # Override user dirs AFTER helper builds env (so PATH/Qt stay intact).
    env = dict(env)
    env["FREECAD_USER_HOME"] = str(profile)
    env["FREECAD_USER_DATA"] = str(profile)
    env["FREECAD_USER_TEMP"] = str(profile / "temp")

    print("Starting isolated FreeCAD:")
    print(f"  exe:     {freecad}")
    print(f"  cmd:     {cmd}")
    print(f"  profile: {profile}")
    print(f"  RPC:     127.0.0.1:{isolated_port}")
    print("  (existing default MCP :9875 left untouched)")

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    process = subprocess.Popen(
        cmd,
        env=env,
        cwd=cwd,
        creationflags=creationflags,
        close_fds=True,
    )
    print(f"  pid:     {process.pid}")

    # Wait briefly for isolated RPC (do not dial :9875).
    deadline = time.time() + 60
    proxy = xmlrpc.client.ServerProxy(
        f"http://127.0.0.1:{isolated_port}", allow_none=True
    )
    while time.time() < deadline:
        if process.poll() is not None:
            print(
                f"ERROR: FreeCAD exited before RPC ready (code {process.returncode})",
                file=sys.stderr,
            )
            return process.returncode or 1
        try:
            if proxy.ping():
                print(f"Isolated MCP RPC ready on 127.0.0.1:{isolated_port}")
                return 0
        except Exception:
            pass
        time.sleep(0.5)

    print(
        f"WARNING: FreeCAD started but RPC on :{isolated_port} not ready yet. "
        "Switch to MCP Addon workbench and Start RPC Server if needed.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
