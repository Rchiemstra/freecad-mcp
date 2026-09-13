"""Native document fixtures for typed G-features-p3 qualification."""

from __future__ import annotations


def run_kwargs(base: dict[str, object], document_name: str, overrides: dict[str, object]) -> dict[str, object]:
    payload = dict(base)
    payload["doc_name"] = document_name
    payload.update(overrides)
    return payload


def prepare_native_document(document, kind: str) -> None:
    import FreeCAD
    import Part

    if kind == "boolean":
        document.addObject("Part::Box", "Shape1")
        tool = document.addObject("Part::Box", "Shape2")
        tool.Placement.Base = FreeCAD.Vector(5, 0, 0)
        document.recompute()
        return

    body = document.addObject("PartDesign::Body", "Body")
    if kind in {"edge_feature", "pattern"}:
        base = body.newObject("PartDesign::Feature", "Pad")
        base.Shape = Part.makeBox(10, 10, 10)
        body.Tip = base
        document.recompute()
        return

    if kind == "profile":
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(
            Part.Circle(FreeCAD.Vector(10, 0, 0), FreeCAD.Vector(0, 0, 1), 3)
        )
        document.recompute()
        return

    if kind == "loft":
        first = body.newObject("Sketcher::SketchObject", "Sketch1")
        first.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 5))
        second = body.newObject("Sketcher::SketchObject", "Sketch2")
        second.Placement.Base = FreeCAD.Vector(0, 0, 10)
        second.addGeometry(Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 3))
        document.recompute()
        return

    if kind == "sweep":
        profile = body.newObject("Sketcher::SketchObject", "Sketch")
        profile.addGeometry(
            Part.Circle(FreeCAD.Vector(10, 0, 0), FreeCAD.Vector(0, 0, 1), 2)
        )
        path = body.newObject("Sketcher::SketchObject", "Path")
        path.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
        path.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 20, 0))
        )
        document.recompute()
        return

    raise KeyError(kind)
