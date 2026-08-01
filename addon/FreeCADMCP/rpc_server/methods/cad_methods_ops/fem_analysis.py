"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from ...fem_executor import run_fem_analysis as run_fem_analysis_impl


def run_fem_analysis(
    self, doc_name: str, analysis_name: str, timeout: int = 600
) -> dict[str, Any]:
    """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
    try:
        timeout_s = int(timeout)
    except (TypeError, ValueError):
        return {"success": False, "error": f"invalid timeout: {timeout!r}"}
    res = self._dispatch_gui(
        lambda: run_fem_analysis_gui(doc_name, analysis_name),
        timeout=timeout_s,
    )
    if isinstance(res, dict):
        return res
    return {"success": False, "error": str(res)}


def run_fem_analysis_gui(doc_name: str, analysis_name: str):
    return run_fem_analysis_impl(doc_name, analysis_name)
