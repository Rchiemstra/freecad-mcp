"""Extract FEM result metrics after a successful solver run."""

from __future__ import annotations


def extract_result_metrics(doc, analysis) -> dict:
    result_obj = None
    for member in analysis.Group:
        if "Result" in getattr(member, "TypeId", "") and hasattr(member, "vonMises"):
            result_obj = member
            break
    if result_obj is None:
        return {
            "success": False,
            "error": "Solver ran but no result object was produced.",
        }

    vm = list(getattr(result_obj, "vonMises", None) or [])
    disp = list(getattr(result_obj, "DisplacementLengths", None) or [])
    doc.recompute()

    return {
        "success": True,
        "result_object": result_obj.Name,
        "node_count": len(vm),
        "max_von_mises_MPa": max(vm) if vm else None,
        "min_von_mises_MPa": min(vm) if vm else None,
        "max_displacement_mm": max(disp) if disp else None,
    }
