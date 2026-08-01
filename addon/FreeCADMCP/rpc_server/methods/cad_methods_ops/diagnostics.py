"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

import FreeCAD


def diagnose_parametric(self, doc_name: str, object_name=None) -> dict:
    res = self._dispatch_gui(
        lambda: diagnose_parametric_gui(doc_name, object_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def diagnose_parametric_gui(doc_name, object_name=None):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        targets = [doc.getObject(object_name)] if object_name else list(doc.Objects)
        targets = [t for t in targets if t is not None]
        if object_name and not targets:
            return f"Object '{object_name}' not found."
        invalid = []
        expression_issues = []
        sketches = []
        for obj in targets:
            state = list(getattr(obj, "State", []))
            if any(s in ("Invalid", "Error") for s in state):
                invalid.append(
                    {
                        "name": obj.Name,
                        "label": getattr(obj, "Label", obj.Name),
                        "type": getattr(obj, "TypeId", ""),
                        "state": state,
                    }
                )
            for item in getattr(obj, "ExpressionEngine", None) or []:
                try:
                    prop = (
                        str(item[0])
                        if isinstance(item, (list, tuple)) and len(item) >= 1
                        else "?"
                    )
                    expr = (
                        str(item[1])
                        if isinstance(item, (list, tuple)) and len(item) >= 2
                        else str(item)
                    )
                    bound = (
                        obj.getExpression(prop)
                        if hasattr(obj, "getExpression")
                        else None
                    )
                    if bound is None and expr:
                        expression_issues.append(
                            {
                                "object": obj.Name,
                                "prop": prop,
                                "expression": expr,
                                "issue": "missing_binding",
                            }
                        )
                except Exception as e:
                    expression_issues.append(
                        {
                            "object": obj.Name,
                            "issue": "expression_error",
                            "message": str(e),
                        }
                    )
            if getattr(obj, "TypeId", "") == "Sketcher::SketchObject":
                sketches.append(
                    {
                        "name": obj.Name,
                        "geometry_count": len(getattr(obj, "Geometry", []) or []),
                        "constraint_count": len(
                            getattr(obj, "Constraints", []) or []
                        ),
                        "state": state,
                        "conflicting": list(
                            getattr(obj, "ConflictingConstraints", []) or []
                        ),
                        "redundant": list(
                            getattr(obj, "RedundantConstraints", []) or []
                        ),
                        "malformed": list(
                            getattr(obj, "MalformedConstraints", []) or []
                        ),
                    }
                )
        return {
            "success": len(invalid) == 0 and len(expression_issues) == 0,
            "document": doc.Name,
            "object": object_name,
            "invalid_objects": invalid,
            "expression_issues": expression_issues,
            "sketches": sketches,
        }
    except Exception as e:
        return str(e)


def get_sketch_diagnostics(self, doc_name: str, sketch_name: str) -> dict:
    """Return solver diagnostics for a Sketcher sketch (read-only)."""
    res = self._dispatch_gui(
        lambda: get_sketch_diagnostics_gui(doc_name, sketch_name)
    )
    return res if isinstance(res, dict) else {"error": res}


def get_sketch_diagnostics_gui(doc_name: str, sketch_name: str) -> dict:
    doc = FreeCAD.getDocument(doc_name)
    if not doc:
        return {"error": f"Document '{doc_name}' not found"}
    sk = doc.getObject(sketch_name)
    if not sk:
        return {"error": f"Sketch '{sketch_name}' not found"}
    info = {
        "name": sk.Name,
        "geometry_count": len(sk.Geometry) if hasattr(sk, "Geometry") else 0,
        "constraint_count": len(sk.Constraints)
        if hasattr(sk, "Constraints")
        else 0,
        "state": list(getattr(sk, "State", [])),
        "conflicting_constraints": list(getattr(sk, "ConflictingConstraints", [])),
        "redundant_constraints": list(getattr(sk, "RedundantConstraints", [])),
        "malformed_constraints": list(getattr(sk, "MalformedConstraints", [])),
        "solver_message": getattr(sk, "SolverMessage", None),
        "is_closed": None,
    }
    try:
        shape = sk.Shape
        if shape and not shape.isNull():
            info["is_closed"] = shape.isClosed()
    except Exception:
        pass
    return info
