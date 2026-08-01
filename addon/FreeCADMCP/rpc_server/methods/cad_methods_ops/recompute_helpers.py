"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

import FreeCAD


def collect_invalid_objects() -> dict[str, list[dict[str, Any]]]:
    flagged: dict[str, list[dict[str, Any]]] = {}
    for doc_name, doc in FreeCAD.listDocuments().items():
        entries = []
        for obj in doc.Objects:
            try:
                state = list(getattr(obj, "State", []))
                if any(s in ("Invalid", "Error", "Touched") for s in state):
                    entries.append(
                        {
                            "name": obj.Name,
                            "label": getattr(obj, "Label", obj.Name),
                            "state": state,
                        }
                    )
            except Exception:
                pass
        if entries:
            flagged[doc_name] = entries
    return flagged


def classify_recompute_errors(
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
    target_doc: str | None,
) -> dict[str, list[dict[str, Any]]]:
    def _key(doc: str, name: str) -> tuple[str, str]:
        return doc, name

    before_keys = {
        _key(doc, item["name"]) for doc, items in before.items() for item in items
    }
    target_errors: list[dict[str, Any]] = []
    pre_existing: list[dict[str, Any]] = []
    unrelated: list[dict[str, Any]] = []
    for doc, items in after.items():
        for item in items:
            entry = {
                "document": doc,
                "object": item["name"],
                "state": item["state"],
            }
            key = _key(doc, item["name"])
            if target_doc and doc == target_doc:
                if key in before_keys:
                    pre_existing.append(entry)
                else:
                    target_errors.append(entry)
            else:
                unrelated.append(entry)
    return {
        "target_recompute_errors": target_errors,
        "pre_existing_target_errors": pre_existing,
        "unrelated_document_errors": unrelated,
    }


def get_recompute_log(self, doc_name: str) -> list:
    """Return recompute state for every object in a document (read-only)."""
    res = self._dispatch_gui(lambda: get_recompute_log_gui(doc_name))
    return res if isinstance(res, list) else [{"error": res}]


def get_recompute_log_gui(doc_name: str) -> list:
    doc = FreeCAD.getDocument(doc_name)
    if not doc:
        return [{"error": f"Document '{doc_name}' not found"}]
    results = []
    for obj in doc.Objects:
        try:
            st = list(getattr(obj, "State", []))
            exprs = []
            for item in getattr(obj, "ExpressionEngine", None) or []:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        exprs.append(
                            {"prop": str(item[0]), "expression": str(item[1])}
                        )
                    else:
                        exprs.append({"raw": str(item)})
                except Exception as ee:
                    exprs.append({"error": str(ee)})
            entry = {
                "name": obj.Name,
                "label": getattr(obj, "Label", obj.Name),
                "type_id": getattr(obj, "TypeId", ""),
                "state": st,
                "valid": not any(s in ("Invalid", "Error") for s in st),
                "expression_count": len(exprs),
            }
            if exprs:
                entry["expressions"] = exprs
            if any(s in ("Invalid", "Error") for s in st) and exprs:
                entry["expression_hint"] = (
                    "object invalid with bound expressions; check diagnose_parametric"
                )
            results.append(entry)
        except Exception as e:
            results.append({"name": getattr(obj, "Name", "?"), "error": str(e)})
    return results


def recompute_document(self, doc_name: str) -> dict:
    res = self._dispatch_gui(lambda: recompute_document_gui(doc_name))
    return self._adapt_gui_mutation_result(res)


def recompute_document_gui(doc_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        doc.recompute()
        return True
    except Exception as e:
        return str(e)


def undo(self, doc_name: str) -> dict:
    res = self._dispatch_gui(lambda: undo_gui(doc_name))
    return self._adapt_gui_mutation_result(res)


def undo_gui(doc_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        doc.undo()
        return True
    except Exception as e:
        return str(e)


def redo(self, doc_name: str) -> dict:
    res = self._dispatch_gui(lambda: redo_gui(doc_name))
    return self._adapt_gui_mutation_result(res)


def redo_gui(doc_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        doc.redo()
        return True
    except Exception as e:
        return str(e)


def recompute_and_wait(self, doc_name: str) -> dict[str, Any]:
    from ...gui_tools import recompute_and_wait as _recompute_and_wait

    res = self._dispatch_gui(lambda: _recompute_and_wait(doc_name))
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}
