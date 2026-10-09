"""Run CalculiX solver on an existing FEM analysis container."""

from __future__ import annotations

import tempfile
import traceback

import FreeCAD

from .result_extraction import extract_result_metrics
from .solver_resolution import resolve_analysis, resolve_solver


def _analysis_has_mesh(analysis: object) -> bool:
    for member in getattr(analysis, "Group", None) or []:
        if getattr(member, "FemMesh", None) is not None:
            return True
        type_id = str(getattr(member, "TypeId", ""))
        if type_id.startswith("Fem::") and "Mesh" in type_id:
            return True
    return False


def _drop_created_solver(doc: object, analysis: object, solver: object | None) -> None:
    if solver is None:
        return
    group = getattr(analysis, "Group", None)
    if isinstance(group, list) and solver in group:
        group.remove(solver)
    remover = getattr(analysis, "removeObject", None)
    if callable(remover):
        try:
            remover(solver)
        except Exception:
            pass
    name = getattr(solver, "Name", None)
    doc_remover = getattr(doc, "removeObject", None)
    if isinstance(name, str) and callable(doc_remover):
        try:
            doc_remover(name)
        except Exception:
            pass


def run_fem_analysis(doc_name: str, analysis_name: str) -> dict:
    """Run the CalculiX solver on an existing FEM analysis container.

    Always returns a dict with at least ``success`` and ``error``/result keys
    so the caller can pass it through to the wire response unchanged.
    """
    work_dir = None
    stage = "initialization"
    analysis = None
    created_solver = None
    try:
        stage = "document lookup"
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return {"success": False, "error": f"Document '{doc_name}' not found."}

        analysis, error = resolve_analysis(doc, analysis_name)
        if error is not None:
            return error

        if not _analysis_has_mesh(analysis):
            return {
                "success": False,
                "error": "Prerequisites failed: FEM: no mesh object found",
            }

        stage = "solver resolution"
        before = list(getattr(analysis, "Group", None) or [])
        solver = resolve_solver(doc, analysis)
        if solver not in before:
            created_solver = solver

        stage = "femtools import"
        from femtools import ccxtools

        stage = "solver setup"
        fea = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
        fea.update_objects()

        work_dir = tempfile.mkdtemp(prefix="freecad_mcp_fem_")
        fea.setup_working_dir(work_dir)
        fea.setup_ccx()

        stage = "prerequisite check"
        prereq_msg = fea.check_prerequisites()
        if prereq_msg:
            _drop_created_solver(doc, analysis, created_solver)
            created_solver = None
            return {
                "success": False,
                "error": f"Prerequisites failed: {prereq_msg}",
                "working_dir": work_dir,
            }

        stage = "solver execution"
        fea.purge_results()
        if fea.run() is False:
            _drop_created_solver(doc, analysis, created_solver)
            created_solver = None
            return {
                "success": False,
                "error": (
                    "CalculiX solver run failed (fea.run() returned False); "
                    "inspect the .dat/.frd output in working_dir."
                ),
                "working_dir": work_dir,
            }

        stage = "result loading"
        fea.load_results()

        stage = "result extraction"
        metrics = extract_result_metrics(doc, analysis)
        if not metrics.get("success"):
            metrics["working_dir"] = work_dir
            _drop_created_solver(doc, analysis, created_solver)
            created_solver = None
            return metrics
        metrics["working_dir"] = work_dir
        created_solver = None
        return metrics
    except Exception as exc:
        if analysis is not None:
            _drop_created_solver(doc, analysis, created_solver)
        return {
            "success": False,
            "error": f"FEM analysis failed during {stage}: {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "working_dir": work_dir,
        }
