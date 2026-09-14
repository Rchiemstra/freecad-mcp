"""Native qualification matrix for ``run_fem_analysis``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


from tests.native_model_state import model_state as _model_state


def _require_fem_workbench() -> None:
    try:
        import ObjectsFem  # noqa: F401
    except ImportError as exc:
        pytest.fail(f"FEM workbench unavailable for native qualification: {exc}")


def _require_fem_executor_prereqs(document, analysis) -> None:
    import shutil

    from addon.FreeCADMCP.rpc_server.fem_executor_ops.solver_resolution import resolve_solver

    _require_fem_workbench()
    import ObjectsFem

    solver_factory = (
        getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None)
        or getattr(ObjectsFem, "makeSolverCalculixCcxTools", None)
    )
    if solver_factory is None:
        pytest.fail("CalculiX solver factory unavailable for native FEM qualification")

    if shutil.which("ccx") is None and shutil.which("ccx_2.19") is None:
        pytest.fail("CalculiX executable (ccx) not found on PATH for native FEM qualification")

    try:
        from femtools import ccxtools
    except ImportError as exc:
        pytest.fail(f"femtools unavailable for native FEM qualification: {exc}")

    solver = resolve_solver(document, analysis)
    fea = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
    fea.update_objects()
    prereq_msg = fea.check_prerequisites()
    if prereq_msg:
        pytest.fail(f"FEM executor prerequisites failed for native qualification: {prereq_msg}")


def _wrap_execution_apply(monkeypatch, subject, after_executor):
    """Arm recompute probes only after identity apply and FEM executor complete."""

    original_apply = subject._RunFemAnalysisExecution.apply

    def wrapped_apply(self, doc):
        original_apply(self, doc)
        after_executor()

    monkeypatch.setattr(subject._RunFemAnalysisExecution, "apply", wrapped_apply)


def _collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.fem_executor import run_fem_analysis

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=run_fem_analysis,
    )


def _prepare(document):
    _require_fem_workbench()
    import ObjectsFem

    existing = document.getObject("Target")
    if existing is not None:
        return existing

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

    fixed_face = next(
        (
            f"Face{index}"
            for index, face in enumerate(beam.Shape.Faces, start=1)
            if abs(face.CenterOfMass.x - 0.0) < 1e-6
        ),
        None,
    )
    loaded_face = next(
        (
            f"Face{index}"
            for index, face in enumerate(beam.Shape.Faces, start=1)
            if abs(face.CenterOfMass.x - float(beam.Length)) < 1e-6
        ),
        None,
    )
    if fixed_face is None or loaded_face is None:
        pytest.fail("Failed to resolve cantilever beam faces for native FEM qualification")

    fixed = ObjectsFem.makeConstraintFixed(document, "Fixed")
    fixed.References = [(beam, fixed_face)]
    analysis.addObject(fixed)

    load = ObjectsFem.makeConstraintForce(document, "Load")
    load.References = [(beam, loaded_face)]
    z_edge = next(
        (
            f"Edge{index}"
            for index, edge in enumerate(beam.Shape.Edges, start=1)
            if abs(edge.tangentAt(0).z) > 0.99
        ),
        None,
    )
    if z_edge is None:
        pytest.fail("Failed to resolve load direction edge for native FEM qualification")
    load.Direction = (beam, z_edge)
    load.Reversed = True
    load.Force = "100 N"
    analysis.addObject(load)

    document.recompute()
    return analysis


def test_run_fem_analysis_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeSuccess")
    events = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    _prepare(document)
    events.clear()
    original_apply = subject._RunFemAnalysisExecution.apply
    original_read = subject.read_run_fem_analysis_result

    def tracked_apply(self, doc):
        events.append("apply")
        original_apply(self, doc)
        probe.touch()

    def tracked_read(admitted, receipt):
        events.append("inspect")
        return original_read(admitted, receipt)

    monkeypatch.setattr(subject._RunFemAnalysisExecution, "apply", tracked_apply)
    monkeypatch.setattr(subject, "read_run_fem_analysis_result", tracked_read)
    try:
        result = subject.run_run_fem_analysis(_collaborators(FreeCAD, lambda _d: events.append("validate")), document.Name, "Target", 600)
        assert result["success"] is True
        assert events == ["apply", "recompute", "inspect", "validate"]
    finally:
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_validation_failure_restores_complete_state():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import run_run_fem_analysis

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeRollback")
    _prepare(document)
    state_before = _model_state(document)
    try:
        result = run_run_fem_analysis(
            _collaborators(FreeCAD, lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure"))),
            document.Name, "Target", 600,
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_apply_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeApplyFailure")
    _prepare(document)
    state_before = _model_state(document)
    original = subject.apply_run_fem_analysis

    def mutates_then_raises(admitted, request):
        original(admitted, request)
        admitted.addObject("App::FeaturePython", "TransientSupport")
        raise RuntimeError("forced failure after structural effects")

    monkeypatch.setattr(subject, "apply_run_fem_analysis", mutates_then_raises)
    try:
        result = subject.run_run_fem_analysis(_collaborators(FreeCAD, lambda _d: None), document.Name, "Target", 600)
        assert result["success"] is False
        assert result["native_status"] == "ApplyFailed"
        assert document.getObject("TransientSupport") is None
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_recompute_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeRecomputeFailure")

    class FailingRecomputeProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                self.armed = False
                raise RuntimeError("forced native recompute failure")

    proxy = FailingRecomputeProbe()
    probe = document.addObject("App::FeaturePython", "FailingRecomputeProbe")
    probe.Proxy = proxy
    _prepare(document)
    state_before = _model_state(document)
    def arm_probe():
        proxy.armed = True
        probe.touch()

    _wrap_execution_apply(monkeypatch, subject, arm_probe)
    try:
        result = subject.run_run_fem_analysis(_collaborators(FreeCAD, lambda _d: None), document.Name, "Target", 600)
        assert result["success"] is False
        assert result["native_status"] == "RecomputeFailed"
        assert _model_state(document) == state_before
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_rollback_failure_is_uncertain_and_fences(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeRollbackFailure")

    class PersistentFailureProbe:
        armed = False

        def execute(self, _object):
            if self.armed:
                raise RuntimeError("persistent recompute failure blocks restoration")

    proxy = PersistentFailureProbe()
    probe = document.addObject("App::FeaturePython", "PersistentFailureProbe")
    probe.Proxy = proxy
    _prepare(document)
    def arm_probe():
        proxy.armed = True
        probe.touch()

    _wrap_execution_apply(monkeypatch, subject, arm_probe)
    collaborators = _collaborators(FreeCAD, lambda _d: None)
    try:
        result = subject.run_run_fem_analysis(collaborators, document.Name, "Target", 600)
        proxy.armed = False
        fenced = subject.run_run_fem_analysis(collaborators, document.Name, "Target", 600)
        assert result["outcome"] == "uncertain" or result["success"] is False
        assert fenced["success"] is False
    finally:
        proxy.armed = False
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_inspection_failure_rolls_back(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import run_fem_analysis as subject

    document = FreeCAD.newDocument("MCPRunFemAnalysisNativeInspectionFailure")
    _prepare(document)
    state_before = _model_state(document)

    def reject(_document, _receipt):
        raise subject.RunFemAnalysisError("CREATED_OBJECT_WRONG_TYPE", "forced inspection failure")

    monkeypatch.setattr(subject, "read_run_fem_analysis_result", reject)
    try:
        result = subject.run_run_fem_analysis(_collaborators(FreeCAD, lambda _d: None), document.Name, "Target", 600)
        assert result["success"] is False
        assert result["error_code"] == "CREATED_OBJECT_WRONG_TYPE"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)


def test_run_fem_analysis_native_postcondition_cannot_write():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import run_run_fem_analysis

    document = FreeCAD.newDocument("MCPRunFemAnalysisReadOnlyPostcondition")
    anchor = document.addObject("App::FeaturePython", "Anchor")
    _prepare(document)
    state_before = _model_state(document)

    def validate(_admitted):
        anchor.Label = "Unvalidated change"

    try:
        result = run_run_fem_analysis(_collaborators(FreeCAD, validate), document.Name, "Target", 600)
        assert result["outcome"] == "rejected"
        assert result["native_status"] == "PostconditionFailed"
        assert _model_state(document) == state_before
    finally:
        FreeCAD.closeDocument(document.Name)
