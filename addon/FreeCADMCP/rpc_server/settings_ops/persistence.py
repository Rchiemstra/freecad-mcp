"""Settings file load, save, and atomic persistence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile

import FreeCAD

from .constants import DEFAULT_SETTINGS, SETTINGS_FILENAME
from .validation import fail_closed_settings, validate_settings


def get_settings_path(*, freecad=None):
    freecad = FreeCAD if freecad is None else freecad
    return os.path.join(freecad.getUserAppDataDir(), SETTINGS_FILENAME)


def atomic_write_settings(path, settings):
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=SETTINGS_FILENAME + ".", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        with contextlib.suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def load_settings(*, freecad=None):
    freecad = FreeCAD if freecad is None else freecad
    path = get_settings_path(freecad=freecad)
    if os.path.exists(path):
        try:
            with open(path) as f:
                settings = json.load(f)
            if not isinstance(settings, dict):
                from .settings_policy_error import SettingsPolicyError

                raise SettingsPolicyError("settings root must be a JSON object")
            needs_mode_migration = "document_lease_mode" not in settings
            validated = validate_settings(settings)
            if needs_mode_migration:
                try:
                    atomic_write_settings(path, validated)
                except Exception as exc:
                    freecad.Console.PrintWarning(
                        f"Loaded but could not persist MCP lease-mode migration: {exc}\n"
                    )
            return validated
        except Exception as e:
            freecad.Console.PrintWarning(f"Failed to load MCP settings: {e}\n")
            return fail_closed_settings(e)
    return validate_settings(DEFAULT_SETTINGS)


def save_settings(settings, *, freecad=None):
    freecad = FreeCAD if freecad is None else freecad
    path = get_settings_path(freecad=freecad)
    try:
        from .settings_policy_error import SettingsPolicyError

        if not isinstance(settings, dict) or settings.get("_configuration_error"):
            raise SettingsPolicyError(
                "refusing to overwrite an invalid settings file; repair it explicitly"
            )
        settings = validate_settings(settings)
        atomic_write_settings(path, settings)
    except Exception as e:
        freecad.Console.PrintError(f"Failed to save MCP settings: {e}\n")
