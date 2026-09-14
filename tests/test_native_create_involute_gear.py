"""Native qualification matrix for typed ``create_involute_gear``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, "Gear", 12, 2.0, 5.0)
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Gear", 12, 2.0, 5.0)


def test_create_involute_gear_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_involute_gear", _KIND, _RUN_ARGS, monkeypatch)


def test_create_involute_gear_native_pad_width_survives_recompute():
    from tests.assembly_io_native_matrix import collaborators, require_native_collaboration

    require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_involute_gear import (
        run_create_involute_gear,
    )

    document = FreeCAD.newDocument("MCPInvoluteGearWidth")
    try:
        result = run_create_involute_gear(
            collaborators(FreeCAD, lambda _d: None),
            document.Name,
            "Gear",
            12,
            2.0,
            5.0,
        )
        assert result["success"] is True, result
        feature = document.getObject(result.get("feature") or "Gear")
        assert feature is not None
        length = getattr(feature.Length, "Value", feature.Length)
        assert abs(float(length) - 5.0) <= 1e-6
        assert not feature.Shape.isNull()
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_involute_gear_native_validation_failure_restores():
    check_validation_failure("create_involute_gear", _KIND, _RUN_ARGS)


def test_create_involute_gear_native_missing_document_keeps_typed_error():
    check_missing_document("create_involute_gear", _RUN_ARGS_MISSING)
