"""Resolve FEM analysis and CalculiX solver objects."""

from __future__ import annotations

import ObjectsFem


def resolve_analysis(doc, analysis_name: str) -> tuple[object | None, dict | None]:
    analysis = doc.getObject(analysis_name)
    if analysis is None:
        return None, {"success": False, "error": f"Analysis '{analysis_name}' not found."}
    if analysis.TypeId not in ("Fem::FemAnalysis", "Fem::FemAnalysisPython"):
        return None, {
            "success": False,
            "error": (
                f"'{analysis_name}' is not a FEM analysis "
                f"(TypeId={analysis.TypeId})."
            ),
        }
    return analysis, None


def resolve_solver(doc, analysis) -> object:
    for member in analysis.Group:
        tid = getattr(member, "TypeId", "")
        if "SolverCcx" in tid or "SolverCalculix" in tid:
            return member
    solver_factory = (
        getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None)
        or getattr(ObjectsFem, "makeSolverCalculixCcxTools", None)
    )
    if solver_factory is None:
        raise RuntimeError("ObjectsFem has no Calculix solver factory.")
    solver = solver_factory(doc, "CalculiX")
    analysis.addObject(solver)
    return solver
