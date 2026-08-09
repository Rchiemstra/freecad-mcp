from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .module_aliases import install_module_aliases

_runtime_lease_mode: str | None = None


def _settings_path_impl() -> Path:
    try:
        import FreeCAD

        return Path(FreeCAD.getUserAppDataDir()) / "freecad_mcp_settings.json"
    except ImportError:
        return Path.home() / "freecad_mcp_settings.json"


def _settings_path() -> Path:
    from .facade_surfaces import resolve_settings_path

    return resolve_settings_path()


def _read_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {
            "document_lease_mode": "observe",
            "enable_document_lock": True,
            "document_lock_enforcement": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "document_lease_mode": "enforce",
        "enable_document_lock": True,
        "document_lock_enforcement": True,
        "_configuration_error": "invalid document lease settings",
    }


def configure_runtime_lease_mode(mode: str) -> None:
    """Latch one validated mode for the lifetime of the lease runtime."""

    normalized = str(mode or "")
    if normalized not in {"off", "observe", "enforce"}:
        raise ValueError("document lease mode must be off, observe, or enforce")
    global _runtime_lease_mode
    _runtime_lease_mode = normalized


def get_runtime_lease_mode() -> str | None:
    return _runtime_lease_mode


def is_enabled() -> bool:
    """True when document lock infrastructure (observer/GUI/sidecars) is on."""
    if _runtime_lease_mode is not None:
        return _runtime_lease_mode != "off"
    data = _read_settings()
    mode = data.get("document_lease_mode")
    if mode in {"off", "observe", "enforce"}:
        return mode != "off"
    return bool(data.get("enable_document_lock", False))


def is_enforcement_enabled() -> bool:
    """True when mutating RPC verbs must present a valid owned lease."""
    if _runtime_lease_mode is not None:
        return _runtime_lease_mode == "enforce"
    data = _read_settings()
    mode = data.get("document_lease_mode")
    if mode in {"off", "observe", "enforce"}:
        return mode == "enforce"
    return bool(data.get("document_lock_enforcement", False)) and bool(
        data.get("enable_document_lock", False)
    )


install_module_aliases(__name__)
