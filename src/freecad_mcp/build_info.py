"""Canonical build metadata for the MCP package.

The module intentionally does not inspect ``.git``.  Release/CI jobs may inject
metadata through environment variables or by generating
``freecad_mcp._build_metadata``.  Installed wheels therefore report the exact
metadata they were built with, while editable/source installs have a stable,
explicit ``unknown`` fallback.
"""

from __future__ import annotations

import os
from importlib import metadata
from typing import Any

from .server_ops.runtime_identity import sanitize_git_commit

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
        from ._build_metadata import (
            BUILD_ID,
            BUILD_TIMESTAMP,
            GIT_COMMIT,
            GIT_DIRTY,
        )
    except ImportError:
        return {}
    return {
        "git_commit": GIT_COMMIT,
        "git_dirty": GIT_DIRTY,
        "build_timestamp": BUILD_TIMESTAMP,
        "build_id": BUILD_ID,
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


def _environment_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for env_name, key in (
        ("FREECAD_MCP_GIT_COMMIT", "git_commit"),
        ("FREECAD_MCP_GIT_DIRTY", "git_dirty"),
        ("FREECAD_MCP_BUILD_TIMESTAMP", "build_timestamp"),
        ("FREECAD_MCP_BUILD_ID", "build_id"),
    ):
        if os.environ.get(env_name) is not None:
            overrides[key] = os.environ.get(env_name)
    return overrides


def compiled_identity() -> dict[str, Any]:
    version = _installed_version()
    fallback_build_id = f"{PACKAGE_NAME}-{version}+unknown"
    generated = _generated_metadata()
    overrides = _environment_overrides()

    if overrides:
        source = "environment"
        git_commit = sanitize_git_commit(
            overrides.get("git_commit", generated.get("git_commit"))
        )
        git_dirty = _optional_bool("FREECAD_MCP_GIT_DIRTY", overrides.get("git_dirty"))
        if "FREECAD_MCP_GIT_DIRTY" not in os.environ:
            git_dirty = _optional_bool("FREECAD_MCP_GIT_DIRTY", generated.get("git_dirty"))
        build_timestamp = _optional_text(
            "FREECAD_MCP_BUILD_TIMESTAMP",
            overrides.get("build_timestamp", generated.get("build_timestamp")),
            "unknown",
        )
        build_id = _optional_text(
            "FREECAD_MCP_BUILD_ID",
            overrides.get("build_id", generated.get("build_id")),
            fallback_build_id,
        )
    elif any(value is not None for value in generated.values()):
        source = "generated_metadata"
        git_commit = sanitize_git_commit(generated.get("git_commit"))
        git_dirty = _optional_bool("FREECAD_MCP_GIT_DIRTY", generated.get("git_dirty"))
        build_timestamp = _optional_text(
            "FREECAD_MCP_BUILD_TIMESTAMP", generated.get("build_timestamp"), "unknown"
        )
        build_id = _optional_text(
            "FREECAD_MCP_BUILD_ID", generated.get("build_id"), fallback_build_id
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


def checkout_identity() -> dict[str, Any]:
    from .server_ops.runtime_identity import read_checkout_git

    return read_checkout_git()


_compiled = compiled_identity()
package_version = _compiled["version"]
git_commit = _compiled["git_commit"]
git_dirty = _compiled["git_dirty"]
build_timestamp = _compiled["build_timestamp"]
build_id = _compiled["build_id"]
protocol_version = PROTOCOL_VERSION
event_schema_version = EVENT_SCHEMA_VERSION


def as_dict() -> dict[str, Any]:
    """Return public, credential-free build metadata for the current request."""

    compiled = compiled_identity()
    checkout = checkout_identity()
    return {
        "version": compiled["version"],
        "build_id": compiled["build_id"],
        "git_commit": compiled["git_commit"],
        "git_dirty": compiled["git_dirty"],
        "build_timestamp": compiled["build_timestamp"],
        "compiled": compiled,
        "checkout": checkout,
        "protocol_version": protocol_version,
        "event_schema_version": event_schema_version,
    }


__all__ = [
    "as_dict",
    "build_id",
    "build_timestamp",
    "checkout_identity",
    "compiled_identity",
    "event_schema_version",
    "git_commit",
    "git_dirty",
    "package_version",
    "protocol_version",
]
