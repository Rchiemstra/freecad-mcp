"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any


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
    collaborators = self._cad_collaborators
    res = self._dispatch_gui(
        lambda: collaborators.repair_references_gui(
            doc_name,
            repairs,
            recompute=bool(recompute),
            validate=bool(validate),
        )
    )
    if isinstance(res, dict):
        return res
    return {"ok": False, "repair_committed": False, "error": str(res)}
