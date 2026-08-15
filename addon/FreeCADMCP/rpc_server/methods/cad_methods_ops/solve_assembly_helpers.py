"""Assembly solve strategy helpers (Phase 4 slice 4F)."""

from __future__ import annotations


def run_assembly_solve(
    asm,
    *,
    allow_recompute_fallback: bool = True,
) -> tuple[str | None, object | None, str | None]:
    error = None
    try:
        if hasattr(asm, "solve"):
            return "assembly.solve()", asm.solve(), None
    except Exception as exc:
        error = str(exc)
    try:
        import JointObject

        JointObject.solveIfAllowed(asm, True)
        return "JointObject.solveIfAllowed", "ok", error
    except Exception as exc:
        error = str(exc) if error is None else f"{error} | {exc}"
    if allow_recompute_fallback:
        try:
            asm.Document.recompute()
            return "recompute", "ok", error
        except Exception as exc:
            error = f"{error} | {exc}" if error else str(exc)
    return None, None, error or "no Assembly solver entry point is available"
