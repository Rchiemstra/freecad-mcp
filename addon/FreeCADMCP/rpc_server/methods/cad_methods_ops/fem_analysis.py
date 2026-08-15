"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from .cad_mutation import unsupported_native_phase_boundary


def run_fem_analysis(
    self, doc_name: str, analysis_name: str, timeout: int = 600
) -> dict[str, Any]:
    """Fail closed until CalculiX can use a phase-aware native mutation boundary."""
    try:
        int(timeout)
    except (TypeError, ValueError):
        return {"success": False, "error": f"invalid timeout: {timeout!r}"}
    return unsupported_native_phase_boundary(
        "run_fem_analysis",
        (
            "CalculiX setup/execution/result loading owns intermediate model "
            "updates that cannot be partitioned around one native recompute"
        ),
    )


def run_fem_analysis_gui(doc_name: str, analysis_name: str, *, run_fem_analysis):
    return run_fem_analysis(doc_name, analysis_name)
