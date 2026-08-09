"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from ...fem_executor_ops.solver_resolution import defer_fem_presentation
from .cad_mutation import run_cad_mutation


def run_fem_analysis(
    self, doc_name: str, analysis_name: str, timeout: int = 600
) -> dict[str, Any]:
    """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
    try:
        timeout_s = int(timeout)
    except (TypeError, ValueError):
        return {"success": False, "error": f"invalid timeout: {timeout!r}"}
    collaborators = self._cad_collaborators

    def analysis_task():
        deferred_presentation = None

        def run_model_analysis():
            nonlocal deferred_presentation
            document = collaborators.freecad.getDocument(doc_name)
            with defer_fem_presentation(document) as presentation:
                result = run_fem_analysis_gui(
                    doc_name,
                    analysis_name,
                    run_fem_analysis=collaborators.run_fem_analysis,
                )
            deferred_presentation = presentation
            return result

        result = run_cad_mutation(
            collaborators,
            doc_name,
            run_model_analysis,
            structural=True,
        )
        if (
            isinstance(result, dict)
            and result.get("success") is not False
            and deferred_presentation is not None
        ):
            try:
                deferred_presentation.apply_after_commit()
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"FEM presentation initialization failed: {exc}",
                }
        return result

    res = self._dispatch_gui(analysis_task, timeout=timeout_s)
    if isinstance(res, dict):
        return res
    return {"success": False, "error": str(res)}


def run_fem_analysis_gui(doc_name: str, analysis_name: str, *, run_fem_analysis):
    return run_fem_analysis(doc_name, analysis_name)
