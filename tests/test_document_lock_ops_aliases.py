"""Module identity for document_lock_ops submodules (Phase 5)."""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.unit
def test_freecad_and_package_document_lock_share_registry() -> None:
    import addon.FreeCADMCP.document_lock as package_mod

    freecad_mod = importlib.import_module("document_lock")
    assert freecad_mod is package_mod
    assert sys.modules["document_lock"] is sys.modules["addon.FreeCADMCP.document_lock"]


@pytest.mark.unit
def test_document_lock_ops_settings_importable() -> None:
    mod = importlib.import_module("addon.FreeCADMCP.document_lock_ops.settings")
    assert callable(mod.is_enabled)
