"""Native qualification matrix for typed ``create_helical_gear``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (
    doc_name,
    "Gear",
    6,
    2.0,
    1.0,
    15.0,
    20.0,
    0.0,
    0.0,
    0.0,
    4,
)
_RUN_ARGS_MISSING = lambda _doc, _ctx: (
    "MissingNativeDoc",
    "Gear",
    6,
    2.0,
    1.0,
    15.0,
    20.0,
    0.0,
    0.0,
    0.0,
    4,
)


def test_create_helical_gear_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_helical_gear", _KIND, _RUN_ARGS, monkeypatch)


def test_create_helical_gear_native_height_survives_recompute():
    from tests.assembly_io_native_matrix import collaborators, require_native_collaboration

    require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_helical_gear import (
        run_create_helical_gear,
    )

    document = FreeCAD.newDocument("MCPHelicalGearHeight")
    try:
        result = run_create_helical_gear(
            collaborators(FreeCAD, lambda _d: None),
            document.Name,
            "Gear",
            6,
            2.0,
            1.0,
            15.0,
            20.0,
            0.0,
            0.0,
            0.0,
            4,
        )
        assert result["success"] is True, result
        feature = document.getObject(result.get("feature") or "Gear")
        assert feature is not None
        height = getattr(feature.Height, "Value", feature.Height)
        assert abs(float(height) - 1.0) <= 1e-6
        assert not feature.Shape.isNull()
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_helical_gear_native_validation_failure_restores():
    check_validation_failure("create_helical_gear", _KIND, _RUN_ARGS)


def test_create_helical_gear_native_missing_document_keeps_typed_error():
    check_missing_document("create_helical_gear", _RUN_ARGS_MISSING)
