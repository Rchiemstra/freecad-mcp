"""Native qualification matrix for ``run_fem_analysis``."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def _require_fem_workbench() -> None:
    try:
        import ObjectsFem  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"FEM workbench unavailable for native qualification: {exc}")


def _collaborators(FreeCAD, fem_runner):
    from tests.core_doc_native_matrix import collaborators

    collab = collaborators(FreeCAD, lambda _d: None)
    collab.run_fem_analysis = fem_runner
    return collab


def _fem_executor_success(*_args, **_kwargs):
    return {"success": True}


def _prepare(document):
    _require_fem_workbench()
    import ObjectsFem

    beam = document.addObject("Part::Box", "Beam")
    beam.Length = 100.0
    beam.Width = 10.0
    beam.Height = 10.0
    document.recompute()

    analysis = ObjectsFem.makeAnalysis(document, "Target")
    material = ObjectsFem.makeMaterialSolid(document, "Material")
    material.Material = {
        "Name": "Steel",
        "Density": "7900 kg/m^3",
        "YoungsModulus": "210 GPa",
        "PoissonRatio": "0.3",
    }
    material.References = [(beam, "")]
    analysis.addObject(material)

    mesh = analysis.addObject(ObjectsFem.makeMeshGmsh(document, "Mesh"))[0]
    geom_attr = "Shape" if hasattr(mesh, "Shape") else "Part"
    setattr(mesh, geom_attr, beam)
    mesh.CharacteristicLengthMax = 10.0
    mesh.CharacteristicLengthMin = 5.0
    document.recompute()
    return analysis


def test_run_fem_analysis_native_success_publishes():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import (
        run_run_fem_analysis,
    )

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativePublished")
    try:
        _prepare(document)
        result = run_run_fem_analysis(
            _collaborators(FreeCAD, _fem_executor_success),
            document.Name,
            "Target",
            600,
        )
        assert result["success"] is True
        assert result["outcome"] == "published"
        assert document.getObject("Target") is not None
    finally:
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_missing_document_is_rejected():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import (
        run_run_fem_analysis,
    )

    result = run_run_fem_analysis(
        _collaborators(FreeCAD, _fem_executor_success),
        "MissingNativeDoc",
        "Target",
        600,
    )
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_run_fem_analysis_native_missing_analysis_is_rejected():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import (
        run_run_fem_analysis,
    )

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeMissingAnalysis")
    try:
        result = run_run_fem_analysis(
            _collaborators(FreeCAD, _fem_executor_success),
            document.Name,
            "MissingAnalysis",
            600,
        )
        assert result["success"] is False
        assert result["error_code"] == "OBJECT_NOT_FOUND"
    finally:
        FreeCAD.closeDocument(document.Name)
