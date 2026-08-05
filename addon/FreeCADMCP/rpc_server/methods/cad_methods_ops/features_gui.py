"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from __future__ import annotations


class _DeferredSketchHide:
    """Apply one presentation-only sketch hide after native publication."""

    __slots__ = ("_sketch",)

    def __init__(self, sketch) -> None:
        self._sketch = sketch

    def apply_after_commit(self) -> None:
        self._sketch.Visibility = False


def pad_feature_gui(
    doc_name,
    sketch_name,
    pad_name,
    length,
    body_name,
    symmetric,
    reversed_dir,
    *,
    freecad,
    set_extrusion_symmetric,
    set_feature_bool,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        if body_name and not doc.getObject(body_name):
            return f"Body '{body_name}' not found."
        body = doc.getObject(body_name) if body_name else None
        if not body:
            for obj in doc.Objects:
                if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                    body = obj
                    break

        # Strict PartDesign: never fall back to a loose document-level feature.
        if body is None or body.TypeId != "PartDesign::Body":
            return (
                f"No PartDesign::Body found to own pad '{pad_name}'. Sketch "
                f"'{sketch_name}' is not inside a Body; create a Body first."
            )
        pad = body.newObject("PartDesign::Pad", pad_name)

        pad.Profile = (sketch, [""])
        pad.Length = length
        set_extrusion_symmetric(pad, symmetric)
        set_feature_bool(pad, ("Reversed",), reversed_dir)
        body.Tip = pad
        doc.recompute()
        freecad.Console.PrintMessage(f"Pad '{pad_name}' created in '{doc_name}'.\n")
        return _DeferredSketchHide(sketch)
    except Exception as e:
        return str(e)


def pocket_feature_gui(
    doc_name,
    sketch_name,
    pocket_name,
    length,
    body_name,
    symmetric,
    reversed_dir,
    *,
    freecad,
    set_extrusion_symmetric,
    set_feature_bool,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        if body_name and not doc.getObject(body_name):
            return f"Body '{body_name}' not found."
        body = doc.getObject(body_name) if body_name else None
        if not body:
            for obj in doc.Objects:
                if obj.TypeId == "PartDesign::Body" and sketch in obj.Group:
                    body = obj
                    break

        # Strict PartDesign: never fall back to a loose document-level feature.
        if body is None or body.TypeId != "PartDesign::Body":
            return (
                f"No PartDesign::Body found to own pocket '{pocket_name}'. Sketch "
                f"'{sketch_name}' is not inside a Body; create a Body first."
            )
        pocket = body.newObject("PartDesign::Pocket", pocket_name)

        pocket.Profile = (sketch, [""])
        pocket.Length = length
        set_extrusion_symmetric(pocket, symmetric)
        set_feature_bool(pocket, ("Reversed",), reversed_dir)
        body.Tip = pocket
        doc.recompute()
        freecad.Console.PrintMessage(
            f"Pocket '{pocket_name}' created in '{doc_name}'.\n"
        )
        return _DeferredSketchHide(sketch)
    except Exception as e:
        return str(e)


def body_create_gui(doc_name, body_name, *, freecad):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        if doc.getObject(body_name):
            return f"Object already exists: {body_name}"
        body = doc.addObject("PartDesign::Body", body_name)
        doc.recompute()
        return {"success": True, "body": body.Name}
    except Exception as e:
        return str(e)


def body_set_tip_gui(doc_name, body_name, feature_name, *, freecad):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        body = doc.getObject(body_name)
        if not body:
            return f"Body '{body_name}' not found."
        feat = doc.getObject(feature_name)
        if not feat:
            return f"Feature '{feature_name}' not found."
        body.Tip = feat
        doc.recompute()
        tip = getattr(body, "Tip", None)
        return {
            "success": True,
            "body": body.Name,
            "tip": getattr(tip, "Name", None),
        }
    except Exception as e:
        return str(e)
