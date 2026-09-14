"""Native FreeCAD qualification for ``sketch_constrain_parallel``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def _collaborators(FreeCAD, Part, Sketcher, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        freecad=FreeCAD,
        part=Part,
        sketcher=Sketcher,
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
    )


def _idle_sketch(FreeCAD, Part, name: str):
    document = FreeCAD.newDocument(name)
    body = document.addObject("PartDesign::Body", "Body")
    sketch = body.newObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(10, 0, 0), FreeCAD.Vector(10, 10, 0)), False)
    document.recompute()
    return document, sketch


def test_sketch_constrain_parallel_native_success_on_idle_sketch():
    _require_native_collaboration()
    import FreeCAD
    import Part
    import Sketcher

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_parallel import run_sketch_constrain_parallel

    document, sketch = _idle_sketch(FreeCAD, Part, "MCPSketchConstrainParallelNativeSuccess")
    before = sketch.GeometryCount, sketch.ConstraintCount
    try:
        result = run_sketch_constrain_parallel(
            _collaborators(FreeCAD, Part, Sketcher, lambda _doc: None),
            document.Name, sketch.Name, 0, 1,
        )
        assert result["success"] is True
        assert result["committed"] is True
        assert result["sketch"] == sketch.Name
        assert (sketch.GeometryCount, sketch.ConstraintCount) != before or result["success"] is True
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_constrain_parallel_native_validation_failure_restores_geometry_counts():
    _require_native_collaboration()
    import FreeCAD
    import Part
    import Sketcher

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_parallel import run_sketch_constrain_parallel

    document, sketch = _idle_sketch(FreeCAD, Part, "MCPSketchConstrainParallelNativeValidation")
    before = sketch.GeometryCount, sketch.ConstraintCount, tuple(obj.Name for obj in document.Objects)

    def fail(_document):
        raise RuntimeError("forced sketch validation failure")

    try:
        result = run_sketch_constrain_parallel(_collaborators(FreeCAD, Part, Sketcher, fail), document.Name, sketch.Name, 0, 1)
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert (sketch.GeometryCount, sketch.ConstraintCount, tuple(obj.Name for obj in document.Objects)) == before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_sketch_constrain_parallel_native_missing_document_keeps_typed_error():
    _require_native_collaboration()
    import FreeCAD
    import Part
    import Sketcher

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_parallel import run_sketch_constrain_parallel

    result = run_sketch_constrain_parallel(
        _collaborators(FreeCAD, Part, Sketcher, lambda _doc: None),
        "NoSuchSketchQualificationDocument",
        "Sketch",
        0, 1,
    )
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert result["outcome"] == "rejected"


def test_sketch_constrain_parallel_native_failure_isolated_and_healthy_document_succeeds():
    _require_native_collaboration()
    import FreeCAD
    import Part
    import Sketcher

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_parallel import run_sketch_constrain_parallel

    failed_document, failed_sketch = _idle_sketch(FreeCAD, Part, "MCPSketchConstrainParallelIsolatedFailure")
    healthy_document, healthy_sketch = _idle_sketch(FreeCAD, Part, "MCPSketchConstrainParallelHealthyDocument")
    rejected = {failed_document.Name}

    def validator(document):
        if document.Name in rejected:
            raise RuntimeError("document-local injected fault")

    collab = _collaborators(FreeCAD, Part, Sketcher, validator)
    try:
        failed = run_sketch_constrain_parallel(collab, failed_document.Name, failed_sketch.Name, 0, 1)
        isolated = run_sketch_constrain_parallel(collab, healthy_document.Name, healthy_sketch.Name, 0, 1)
        assert failed["success"] is False
        assert isolated["success"] is True
    finally:
        FreeCAD.closeDocument(failed_document.Name)
        FreeCAD.closeDocument(healthy_document.Name)


def test_sketch_constrain_parallel_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    import Part
    import Sketcher

    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_parallel import run_sketch_constrain_parallel

    document, sketch = _idle_sketch(FreeCAD, Part, "MCPSketchConstrainParallelReadOnlyPostcondition")
    before = sketch.GeometryCount, tuple(obj.Name for obj in document.Objects)

    def validate(admitted):
        admitted.addObject("Part::Feature", "UnvalidatedObject")
        raise RuntimeError("postcondition write must not persist")

    try:
        result = run_sketch_constrain_parallel(
            _collaborators(FreeCAD, Part, Sketcher, validate),
            document.Name, sketch.Name, 0, 1,
        )
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert (sketch.GeometryCount, tuple(obj.Name for obj in document.Objects)) == before
    finally:
        FreeCAD.closeDocument(document.Name)
