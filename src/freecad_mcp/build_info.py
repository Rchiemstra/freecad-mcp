"""Canonical build metadata for the MCP package.

The module intentionally does not inspect ``.git``.  Release/CI jobs may inject
metadata through environment variables or by generating
``freecad_mcp._build_metadata``.  Installed wheels therefore report the exact
metadata they were built with, while editable/source installs have a stable,
explicit ``unknown`` fallback.
"""

from __future__ import annotations

from importlib import metadata
import os
from typing import Any


PACKAGE_NAME = "freecad-mcp"
PROTOCOL_VERSION = 2
EVENT_SCHEMA_VERSION = 1


def _installed_version() -> str:
    try:
        return metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _generated_metadata() -> dict[str, Any]:
    try:
        from . import _build_metadata
    except ImportError:
        return {}
    return {
        "git_commit": getattr(_build_metadata, "GIT_COMMIT", None),
        "git_dirty": getattr(_build_metadata, "GIT_DIRTY", None),
        "build_timestamp": getattr(_build_metadata, "BUILD_TIMESTAMP", None),
        "build_id": getattr(_build_metadata, "BUILD_ID", None),
    }


def _optional_text(environment_name: str, generated: Any, fallback: str) -> str:
    value = os.environ.get(environment_name)
    if value is None:
        value = generated
    rendered = str(value).strip() if value is not None else ""
    return rendered or fallback


def _optional_bool(environment_name: str, generated: Any) -> bool | None:
    value = os.environ.get(environment_name)
    if value is None:
        value = generated
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


package_version = _installed_version()
_generated = _generated_metadata()
git_commit = _optional_text(
    "FREECAD_MCP_GIT_COMMIT", _generated.get("git_commit"), "unknown"
)
git_dirty = _optional_bool("FREECAD_MCP_GIT_DIRTY", _generated.get("git_dirty"))
build_timestamp = _optional_text(
    "FREECAD_MCP_BUILD_TIMESTAMP", _generated.get("build_timestamp"), "unknown"
)
_fallback_build_id = f"{PACKAGE_NAME}-{package_version}+unknown"
build_id = _optional_text(
    "FREECAD_MCP_BUILD_ID", _generated.get("build_id"), _fallback_build_id
)
protocol_version = PROTOCOL_VERSION
event_schema_version = EVENT_SCHEMA_VERSION


def as_dict() -> dict[str, Any]:
    """Return public, credential-free build metadata."""

    return {
        "version": package_version,
        "build_id": build_id,
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "build_timestamp": build_timestamp,
        "protocol_version": protocol_version,
        "event_schema_version": event_schema_version,
    }


__all__ = [
    "as_dict",
    "build_id",
    "build_timestamp",
    "event_schema_version",
    "git_commit",
    "git_dirty",
    "package_version",
    "protocol_version",
]
