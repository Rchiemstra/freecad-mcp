"""FreeCADCmd-only reproduction of stress finding 10; no MCP imports.

Run: FreeCADCmd scripts/reproduce_round12_offset.py
A plain sketch reproduces the element-map warning on successive recomputes.
"""
import FreeCAD as App
import Part


doc = App.newDocument('PlainOffset')
sketch = doc.addObject('Sketcher::SketchObject', 'Sketch')
for start, end in [((0, 0), (10, 0)), ((10, 0), (10, 10)),
                   ((0, 1.5), (10, 1.5)), ((8.5, 0), (8.5, 10))]:
    sketch.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)), False)
for index in range(3):
    print('Plain FreeCAD recompute', index)
    doc.recompute()
    sketch.touch()
App.closeDocument(doc.Name)
