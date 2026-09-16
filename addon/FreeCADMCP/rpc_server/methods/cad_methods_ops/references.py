"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from .cad_mutation import run_cad_mutation


def inspect_references(
    self,
    doc_name: str,
    object_names: list[str] | None = None,
    only_invalid: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    """Inspect link properties without serializing shapes or recomputing."""
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: collaborators.inspect_references_gui(
            doc_name,
            object_names,
            only_invalid=bool(only_invalid),
            validate=bool(validate),
        )
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


def repair_references(
    self,
    doc_name: str,
    repairs: list[dict[str, Any]],
    recompute: bool = False,
    validate: bool = False,
) -> dict[str, Any]:
    """Atomically rewrite link properties, deferring recompute by default."""
    if recompute:
        return {
            "success": False,
            "ok": False,
            "repair_committed": False,
            "error_code": "RECOMPUTE_DEFERRED",
            "error": (
                "repair_references defers coordinator-owned recompute; "
                "call recompute_document after repair"
            ),
        }
    collaborators = self._cad_collaborators

    def apply_repairs():
        return collaborators.repair_references_gui(
            doc_name,
            repairs,
            recompute=False,
            validate=bool(validate),
            phase="complete",
        )

    res = self._dispatch_gui(
        lambda: run_cad_mutation(
            collaborators,
            doc_name,
            apply_repairs,
            native_recompute=False,
            method="repair_references",
        )
    )
    if isinstance(res, dict):
        if res.get("success") is False or res.get("ok") is False:
            res = dict(res)
            res["repair_committed"] = False
        return res
    return {"ok": False, "repair_committed": False, "error": str(res)}
