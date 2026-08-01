"""Assembly solve GUI handler (Phase 4 slice 4F)."""

import contextlib

import FreeCAD

from .solve_assembly_helpers import run_assembly_solve


def solve_assembly(self, doc_name: str, assembly_name: str) -> dict:
    """I9 — re-solve an Assembly via the real internal solver. Tries
    assembly.solve() (C++), then JointObject.solveIfAllowed, then recompute."""
    def solve_task():
        return solve_assembly_gui(doc_name, assembly_name)

    res = self._dispatch_gui(solve_task)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": res}


def solve_assembly_gui(doc_name: str, assembly_name: str):
    try:
        doc = FreeCAD.getDocument(doc_name)
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
        method, status, error = run_assembly_solve(asm)
        if method is None:
            return {"ok": False, "error": f"solve_assembly failed: {error}"}
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
