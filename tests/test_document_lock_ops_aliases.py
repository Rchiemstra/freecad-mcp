"""Module identity for document_lock and document_lock_ops (Phase 5)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ADDON_ROOT = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
_DOCUMENT_LOCK_OPS_SUBMODULES = tuple(
    sorted(
        path.stem
        for path in (_ADDON_ROOT / "document_lock_ops").glob("*.py")
        if path.name != "__init__.py"
    )
)


def _assert_flat_package_identity(*, canonical: str, flat: str) -> None:
    canonical_mod = importlib.import_module(canonical)
    flat_mod = importlib.import_module(flat)
    assert flat_mod is canonical_mod
    assert sys.modules[canonical] is sys.modules[flat]
    assert sys.modules[canonical] is canonical_mod


@pytest.mark.unit
def test_freecad_and_package_document_lock_share_registry() -> None:
    import addon.FreeCADMCP.document_lock as package_mod

    freecad_mod = importlib.import_module("document_lock")
    assert freecad_mod is package_mod
    assert sys.modules["document_lock"] is sys.modules["addon.FreeCADMCP.document_lock"]


@pytest.mark.unit
@pytest.mark.parametrize("submodule", _DOCUMENT_LOCK_OPS_SUBMODULES)
def test_document_lock_ops_submodule_flat_package_identity(submodule: str) -> None:
    # Import the facade first so its post-import alias loop runs.
    importlib.import_module("addon.FreeCADMCP.document_lock")
    _assert_flat_package_identity(
        canonical=f"addon.FreeCADMCP.document_lock_ops.{submodule}",
        flat=f"document_lock_ops.{submodule}",
    )
