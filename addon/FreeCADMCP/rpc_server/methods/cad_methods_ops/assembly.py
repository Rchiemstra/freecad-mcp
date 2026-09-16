"""Assembly solve GUI handler (Phase 4 slice 4F)."""

import contextlib

from .cad_mutation import run_cad_mutation, unsupported_native_phase_boundary
from .solve_assembly_helpers import run_assembly_solve


def solve_assembly(self, doc_name: str, assembly_name: str) -> dict:
    """Re-solve through an apply-only solver, then native authoritative recompute."""
    collaborators = self._cad_collaborators

    def solve_task():
        return run_cad_mutation(
            collaborators,
            doc_name,
            lambda: solve_assembly_gui(
                doc_name,
                assembly_name,
                freecad=collaborators.freecad,
                recompute=False,
            ),
            structural=True,
        )

    res = self._dispatch_gui(solve_task)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": res}


def solve_assembly_gui(
    doc_name: str,
    assembly_name: str,
    *,
    freecad,
    recompute: bool = True,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return {"ok": False, "error": f"Document '{doc_name}' not found."}
        asm = doc.getObject(assembly_name)
        if not asm:
            return {"ok": False, "error": f"Assembly '{assembly_name}' not found."}
        try:
            is_asm = asm.isDerivedFrom("Assembly::AssemblyObject")
        except Exception:
            is_asm = False
        if not is_asm:
            return {
                "ok": False,
                "error": f"Object '{assembly_name}' is not an Assembly::AssemblyObject.",
            }
        method, status, error = run_assembly_solve(
            asm,
            allow_recompute_fallback=recompute,
        )
        if method is None:
            if not recompute:
                return unsupported_native_phase_boundary(
                    "solve_assembly",
                    error or "no apply-only Assembly solver entry point is available",
                )
            return {"ok": False, "error": f"solve_assembly failed: {error}"}
        if recompute:
            with contextlib.suppress(Exception):
                doc.recompute()
        return {
            "ok": True,
            "assembly": asm.Name,
            "method": method,
            "status": str(status) if status is not None else None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
