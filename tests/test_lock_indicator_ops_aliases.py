"""Module identity for lock_indicator and lock_indicator_ops (Phase 5)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_ADDON_ROOT = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
_LOCK_INDICATOR_OPS_SUBMODULES = tuple(
    sorted(
        path.stem
        for path in (_ADDON_ROOT / "lock_indicator_ops").glob("*.py")
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
def test_freecad_and_package_lock_indicator_share_registry() -> None:
    import addon.FreeCADMCP.lock_indicator as package_mod

    freecad_mod = importlib.import_module("lock_indicator")
    assert freecad_mod is package_mod
    assert sys.modules["lock_indicator"] is sys.modules["addon.FreeCADMCP.lock_indicator"]


@pytest.mark.unit
@pytest.mark.parametrize("submodule", _LOCK_INDICATOR_OPS_SUBMODULES)
def test_lock_indicator_ops_submodule_flat_package_identity(submodule: str) -> None:
    # Import the facade first so its post-import alias loop runs.
    importlib.import_module("addon.FreeCADMCP.lock_indicator")
    _assert_flat_package_identity(
        canonical=f"addon.FreeCADMCP.lock_indicator_ops.{submodule}",
        flat=f"lock_indicator_ops.{submodule}",
    )
