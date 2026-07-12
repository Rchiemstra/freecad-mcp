#!/usr/bin/env python3
"""Merge the FreeCAD MCP server entry into Cursor ``mcp.json`` files (R5).

Reads existing JSON, preserves unrelated servers, and atomically updates only
the ``freecad`` entry.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _cursor_config_paths() -> list[Path]:
    home = Path.home()
    return [
        home / ".cursor" / "mcp.json",
        home / "Music" / "FreeCADModeling" / "FreeCAD" / ".cursor" / "mcp.json",
        Path.cwd() / ".cursor" / "mcp.json",
    ]


def _freecad_entry(repo_root: Path) -> dict:
    runner = repo_root / "scripts" / "run_freecad_mcp.py"
    if runner.exists():
        return {
            "command": sys.executable,
            "args": [str(runner)],
        }
    return {
        "command": "uvx",
        "args": ["freecad-mcp"],
    }


def merge_config(path: Path, freecad_server: dict) -> bool:
    """Merge *freecad_server* into *path*. Returns True when written."""
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    servers = dict(existing.get("mcpServers", {}))
    servers["freecad"] = freecad_server
    merged = {**existing, "mcpServers": servers}

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
    return True


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    entry = _freecad_entry(repo_root)
    written = []
    for path in _cursor_config_paths():
        if path.parent.exists() or path == Path.cwd() / ".cursor" / "mcp.json":
            merge_config(path, entry)
            written.append(str(path))
    if not written:
        default = Path.home() / ".cursor" / "mcp.json"
        merge_config(default, entry)
        written.append(str(default))
    print("Updated FreeCAD MCP config in:")
    for p in written:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
