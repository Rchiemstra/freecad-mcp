"""Build metadata bundled with the independently installable FreeCAD addon."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _bundled() -> dict[str, Any]:
    try:
        value = json.loads(
            (Path(__file__).with_name("_build_metadata.json")).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError, NameError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(environment: str, bundled: Any, fallback: str) -> str:
    value = os.environ.get(environment)
    if value is None:
        value = bundled
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _dirty(value: Any) -> bool | None:
    environment = os.environ.get("FREECAD_MCP_GIT_DIRTY")
    if environment is not None:
        value = environment
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "dirty"}:
        return True
    if normalized in {"0", "false", "no", "clean"}:
        return False
    return None


_metadata = _bundled()
addon_version = _text(
    "FREECAD_MCP_ADDON_VERSION", _metadata.get("version"), "0+unknown"
)
addon_build_id = _text(
    "FREECAD_MCP_ADDON_BUILD_ID",
    os.environ.get("FREECAD_MCP_BUILD_ID") or _metadata.get("build_id"),
    f"freecad-mcp-{addon_version}+unknown",
)
git_commit = _text(
    "FREECAD_MCP_GIT_COMMIT", _metadata.get("git_commit"), "unknown"
)
git_dirty = _dirty(_metadata.get("git_dirty"))
build_timestamp = _text(
    "FREECAD_MCP_BUILD_TIMESTAMP", _metadata.get("build_timestamp"), "unknown"
)


def as_dict() -> dict[str, Any]:
    return {
        "version": addon_version,
        "build_id": addon_build_id,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "build_timestamp": build_timestamp,
    }


__all__ = [
    "addon_build_id",
    "addon_version",
    "as_dict",
    "build_timestamp",
    "git_commit",
    "git_dirty",
]
