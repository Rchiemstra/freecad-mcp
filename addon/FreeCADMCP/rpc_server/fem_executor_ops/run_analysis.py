"""Run CalculiX solver on an existing FEM analysis container."""

from __future__ import annotations

import tempfile
import traceback

import FreeCAD

from .result_extraction import extract_result_metrics
from .solver_resolution import resolve_analysis, resolve_solver


def run_fem_analysis(doc_name: str, analysis_name: str) -> dict:
    """Run the CalculiX solver on an existing FEM analysis container.

    Always returns a dict with at least ``success`` and ``error``/result keys
    so the caller can pass it through to the wire response unchanged.
    """
    work_dir = None
    stage = "initialization"
    try:
        stage = "document lookup"
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return {"success": False, "error": f"Document '{doc_name}' not found."}

        analysis, error = resolve_analysis(doc, analysis_name)
        if error is not None:
            return error

        stage = "solver resolution"
        solver = resolve_solver(doc, analysis)

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
            return {
                "success": False,
                "error": f"Prerequisites failed: {prereq_msg}",
                "working_dir": work_dir,
            }

        stage = "solver execution"
        fea.purge_results()
        if fea.run() is False:
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
            return metrics
        metrics["working_dir"] = work_dir
        return metrics
    except Exception as exc:
        return {
            "success": False,
            "error": f"FEM analysis failed during {stage}: {type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "working_dir": work_dir,
        }
