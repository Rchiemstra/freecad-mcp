#!/usr/bin/env python3
"""Add Cursor mcpServers entry ``freecad-isolated`` without touching ``freecad``.

Writes/merges only the isolated key into the workspace ``.cursor/mcp.json``.
Aborts if the existing ``freecad`` entry would be modified.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path


ISOLATED_KEY = "freecad-isolated"
ISOLATED_PORT = 9876
PROTECTED_KEY = "freecad"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _freecad_mcp_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _isolated_entry(python_exe: str, runner: Path, src_dir: Path) -> dict:
    return {
        "type": "stdio",
        "command": python_exe,
        "args": [
            str(runner).replace("\\", "/"),
            "--host",
            "127.0.0.1",
            "--port",
            str(ISOLATED_PORT),
        ],
        "env": {
            "PYTHONUNBUFFERED": "1",
            "FREECAD_MCP_PORT": str(ISOLATED_PORT),
            "PYTHONPATH": str(src_dir).replace("\\", "/"),
        },
    }


def merge_isolated(path: Path, entry: dict) -> None:
    existing: dict = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))

    before = deepcopy(existing)
    servers = dict(existing.get("mcpServers", {}))
    protected_before = deepcopy(servers.get(PROTECTED_KEY)) if PROTECTED_KEY in servers else None

    servers[ISOLATED_KEY] = entry
    merged = {**existing, "mcpServers": servers}

    # Guard: freecad key must be byte-identical if it existed.
    after_protected = merged.get("mcpServers", {}).get(PROTECTED_KEY)
    if protected_before is not None and after_protected != protected_before:
        raise SystemExit(
            f"Abort: merge would modify protected key '{PROTECTED_KEY}' in {path}"
        )
    if PROTECTED_KEY in before.get("mcpServers", {}) and PROTECTED_KEY not in merged.get(
        "mcpServers", {}
    ):
        raise SystemExit(
            f"Abort: merge would remove protected key '{PROTECTED_KEY}' in {path}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    repo = _repo_root()
    mcp_root = _freecad_mcp_root()
    runner = mcp_root / "scripts" / "run_freecad_mcp.py"
    if not runner.is_file():
        raise SystemExit(f"Runner not found: {runner}")

    # Prefer a venv python if present under freecad-mcp; else current interpreter.
    venv_py = mcp_root / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_py) if venv_py.is_file() else sys.executable

    entry = _isolated_entry(python_exe.replace("\\", "/"), runner, mcp_root / "src")
    config_path = repo / ".cursor" / "mcp.json"
    merge_isolated(config_path, entry)

    print(f"Updated {config_path}")
    print(f"  added/updated key: {ISOLATED_KEY}")
    print(f"  command: {entry['command']}")
    print(f"  args: {entry['args']}")
    print(f"  protected key '{PROTECTED_KEY}' left unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
