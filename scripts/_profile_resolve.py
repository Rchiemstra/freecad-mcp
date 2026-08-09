"""Shared isolated-profile path resolution for setup/launcher scripts."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PROFILE_NAME = ".freecad-mcp-isolated"


def resolve_isolated_profile(
    repo: Path,
    *,
    profile_name: str | None = None,
    default_name: str = DEFAULT_PROFILE_NAME,
) -> Path:
    """Resolve the isolated profile directory.

    ``FREECAD_MCP_PROFILE_DIR`` wins when set (full path). Otherwise
    ``profile_name`` (or ``default_name``) is joined under ``repo``.
    """

    env_dir = os.environ.get("FREECAD_MCP_PROFILE_DIR")
    if env_dir:
        return Path(env_dir)
    name = profile_name or default_name
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise SystemExit(
            f"Invalid --profile-name {name!r}; use a simple directory name "
            f"(default {default_name!r}) or set FREECAD_MCP_PROFILE_DIR"
        )
    return repo / name
