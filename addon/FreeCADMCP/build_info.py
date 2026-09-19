"""Build metadata bundled with the independently installable FreeCAD addon."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

_PATH_SHAPED_COMMIT = re.compile(
    r"^(?:/proc/|[a-zA-Z]:[/\\]|https?://|.*\.exe$)",
    re.IGNORECASE,
)


def _sanitize_git_commit(value: object) -> str:
    rendered = str(value).strip() if value is not None else ""
    if not rendered:
        return "unknown"
    if "/" in rendered or "\\" in rendered:
        return "unknown"
    if _PATH_SHAPED_COMMIT.search(rendered):
        return "unknown"
    return rendered


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


def _environment_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for env_name, key in (
        ("FREECAD_MCP_GIT_COMMIT", "git_commit"),
        ("FREECAD_MCP_GIT_DIRTY", "git_dirty"),
        ("FREECAD_MCP_BUILD_TIMESTAMP", "build_timestamp"),
        ("FREECAD_MCP_ADDON_BUILD_ID", "build_id"),
        ("FREECAD_MCP_BUILD_ID", "build_id"),
        ("FREECAD_MCP_ADDON_VERSION", "version"),
    ):
        if os.environ.get(env_name) is not None:
            overrides[key] = os.environ.get(env_name)
    return overrides


def compiled_identity() -> dict[str, Any]:
    bundled = _bundled()
    overrides = _environment_overrides()
    version = _text("FREECAD_MCP_ADDON_VERSION", bundled.get("version"), "0+unknown")
    fallback_build_id = f"freecad-mcp-{version}+unknown"

    if overrides:
        source = "environment"
        git_commit = _sanitize_git_commit(
            overrides.get("git_commit", bundled.get("git_commit"))
        )
        git_dirty = _dirty(overrides.get("git_dirty"))
        if "FREECAD_MCP_GIT_DIRTY" not in os.environ:
            git_dirty = _dirty(bundled.get("git_dirty"))
        build_timestamp = _text(
            "FREECAD_MCP_BUILD_TIMESTAMP",
            overrides.get("build_timestamp", bundled.get("build_timestamp")),
            "unknown",
        )
        build_id = _text(
            "FREECAD_MCP_ADDON_BUILD_ID",
            overrides.get("build_id", bundled.get("build_id")),
            fallback_build_id,
        )
    elif bundled:
        source = "generated_metadata"
        git_commit = _sanitize_git_commit(bundled.get("git_commit"))
        git_dirty = _dirty(bundled.get("git_dirty"))
        build_timestamp = _text(
            "FREECAD_MCP_BUILD_TIMESTAMP", bundled.get("build_timestamp"), "unknown"
        )
        build_id = _text(
            "FREECAD_MCP_ADDON_BUILD_ID", bundled.get("build_id"), fallback_build_id
        )
    else:
        source = "missing"
        git_commit = "unknown"
        git_dirty = None
        build_timestamp = "unknown"
        build_id = fallback_build_id

    return {
        "version": version,
        "build_id": build_id,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "build_timestamp": build_timestamp,
        "source": source,
    }


def read_checkout_identity() -> dict[str, Any]:
    """Git identity of the checkout this addon was loaded from.

    Development installs symlink the addon into FreeCAD's Mod directory, so the bundled
    metadata stays ``unknown``; the checkout itself still identifies the loaded code.
    """
    root = str(Path(__file__).resolve().parent)
    unavailable: dict[str, Any] = {"git_commit": "unknown", "git_dirty": None, "available": False}
    try:
        commit = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return unavailable
    commit = _sanitize_git_commit(commit)
    if commit == "unknown":
        return unavailable
    return {"git_commit": commit, "git_dirty": bool(status.strip()), "available": True}


_metadata = compiled_identity()
# Captured once: the imported modules match the checkout as it was at load time.
_checkout = read_checkout_identity()
addon_version = _metadata["version"]
addon_build_id = _metadata["build_id"]
git_commit = _metadata["git_commit"]
git_dirty = _metadata["git_dirty"]
build_timestamp = _metadata["build_timestamp"]


def as_dict() -> dict[str, Any]:
    compiled = compiled_identity()
    return {
        "version": compiled["version"],
        "build_id": compiled["build_id"],
        "git_commit": compiled["git_commit"],
        "git_dirty": compiled["git_dirty"],
        "build_timestamp": compiled["build_timestamp"],
        "compiled": compiled,
        "checkout": dict(_checkout),
    }


__all__ = [
    "addon_build_id",
    "addon_version",
    "as_dict",
    "build_timestamp",
    "compiled_identity",
    "git_commit",
    "git_dirty",
    "read_checkout_identity",
]
