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
def test_freecad_and_package_document_lock_share_registry(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(_ADDON_ROOT))
    import addon.FreeCADMCP.document_lock as package_mod

    freecad_mod = importlib.import_module("document_lock")
    assert freecad_mod is package_mod
    assert sys.modules["document_lock"] is sys.modules[
        "addon.FreeCADMCP.document_lock"
    ]
    package_mod.set_request_identity(pid=17, request_id="shared-alias")
    assert freecad_mod.get_request_identity()["request_id"] == "shared-alias"
    freecad_mod.clear_request_identity()


@pytest.mark.unit
def test_direct_document_lock_submodules_share_state(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(_ADDON_ROOT))
    package_registry = importlib.import_module(
        "addon.FreeCADMCP.document_lock_ops.registry_state"
    )
    flat_registry = importlib.import_module("document_lock_ops.registry_state")
    package_request = importlib.import_module(
        "addon.FreeCADMCP.document_lock_ops.request_identity"
    )
    flat_request = importlib.import_module("document_lock_ops.request_identity")
    package_mutation = importlib.import_module(
        "addon.FreeCADMCP.document_lock_ops.agent_mutation_ops"
    )
    flat_mutation = importlib.import_module(
        "document_lock_ops.agent_mutation_ops"
    )
    package_snapshot = importlib.import_module(
        "addon.FreeCADMCP.document_lock_ops.internal_snapshot_save_ops"
    )
    flat_snapshot = importlib.import_module(
        "document_lock_ops.internal_snapshot_save_ops"
    )

    assert package_registry is flat_registry
    assert package_request is flat_request
    assert package_mutation is flat_mutation
    assert package_snapshot is flat_snapshot
    assert package_registry._registry is flat_registry._registry
    assert package_registry._registry_lock is flat_registry._registry_lock
    assert package_request._request_ctx is flat_request._request_ctx
    assert package_mutation._agent_mutation_ctx is flat_mutation._agent_mutation_ctx
    assert (
        package_snapshot._internal_snapshot_save_ctx
        is flat_snapshot._internal_snapshot_save_ctx
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "facade_name",
    ("addon.FreeCADMCP.document_lock", "document_lock"),
)
def test_each_document_lock_spelling_retains_monkeypatch_surface(
    facade_name: str,
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(_ADDON_ROOT))
    package_mod = importlib.import_module("addon.FreeCADMCP.document_lock")
    flat_mod = importlib.import_module("document_lock")
    facade = importlib.import_module(facade_name)
    surfaces = importlib.import_module(
        "addon.FreeCADMCP.document_lock_ops.facade_surfaces"
    )
    sentinel = object()

    monkeypatch.setattr(facade, "_settings_path", lambda: sentinel)

    assert surfaces.resolve_settings_path() is sentinel
    assert package_mod.list_leases is flat_mod.list_leases


@pytest.mark.unit
@pytest.mark.parametrize("submodule", _DOCUMENT_LOCK_OPS_SUBMODULES)
def test_document_lock_ops_submodule_flat_package_identity(
    submodule: str, monkeypatch
) -> None:
    monkeypatch.syspath_prepend(str(_ADDON_ROOT))
    importlib.import_module("addon.FreeCADMCP.document_lock")
    _assert_flat_package_identity(
        canonical=f"addon.FreeCADMCP.document_lock_ops.{submodule}",
        flat=f"document_lock_ops.{submodule}",
    )
