"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

import FreeCAD


def set_expression(
    self, doc_name: str, object_name: str, prop_path: str, expression: str
) -> dict:
    res = self._dispatch_gui(
        lambda: set_expression_gui(
            doc_name, object_name, prop_path, expression
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def clear_expression(self, doc_name: str, object_name: str, prop_path: str) -> dict:
    res = self._dispatch_gui(
        lambda: clear_expression_gui(doc_name, object_name, prop_path)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def list_expressions(self, doc_name: str, object_name: str) -> dict:
    res = self._dispatch_gui(
        lambda: list_expressions_gui(doc_name, object_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def set_expression_gui(doc_name, object_name, prop_path, expression):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        obj = doc.getObject(object_name)
        if not obj:
            return f"Object '{object_name}' not found."
        try:
            obj.setExpression(prop_path, expression)
        except Exception as e:
            return {
                "success": False,
                "error": "expression_error",
                "object": object_name,
                "prop_path": prop_path,
                "expression": expression,
                "message": str(e),
            }
        doc.recompute()
        state = list(getattr(obj, "State", []))
        invalid = any(s in ("Invalid", "Error") for s in state)
        return {
            "success": not invalid,
            "object": obj.Name,
            "prop_path": prop_path,
            "expression": expression,
            "state": state,
            "valid": not invalid,
        }
    except Exception as e:
        return str(e)


def clear_expression_gui(doc_name, object_name, prop_path):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        obj = doc.getObject(object_name)
        if not obj:
            return f"Object '{object_name}' not found."
        if hasattr(obj, "clearExpression"):
            obj.clearExpression(prop_path)
        else:
            obj.setExpression(prop_path, None)
        doc.recompute()
        return {"success": True, "object": obj.Name, "prop_path": prop_path}
    except Exception as e:
        return str(e)


def list_expressions_gui(doc_name, object_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        obj = doc.getObject(object_name)
        if not obj:
            return f"Object '{object_name}' not found."
        exprs = []
        for item in getattr(obj, "ExpressionEngine", None) or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                exprs.append({"prop": str(item[0]), "expression": str(item[1])})
            else:
                exprs.append({"raw": str(item)})
        return {
            "success": True,
            "object": obj.Name,
            "expressions": exprs,
            "count": len(exprs),
        }
    except Exception as e:
        return str(e)
