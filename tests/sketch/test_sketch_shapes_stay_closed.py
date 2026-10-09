"""Rectangles, polygons and polylines must stay connected when dimensioned.

The segments were only placed end to end. Constraining one edge's length
then moved its end away from its neighbour and the pad failed with "Wire is
not closed". Consecutive segments are now joined with coincident constraints.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_polyline import (
    run_sketch_add_polyline,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_rectangle import (
    run_sketch_add_rectangle,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_regular_polygon import (
    run_sketch_add_regular_polygon,
)
from tests.sketch_exec_support import FakeDocument, collaborators

pytestmark = pytest.mark.unit

_END, _START = 2, 1


def _coincidences(sketch):
    return [c.args[1:] for c in sketch.constraints if c.args[0] == "Coincident"]


def _run(run):
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    result = run(collab)
    assert result["success"] is True, (result.get("error_code"), result.get("error"))
    return document.sketch


def test_a_rectangle_is_closed_by_four_coincidences():
    sketch = _run(lambda c: run_sketch_add_rectangle(c, "Doc", "Sketch", 0, 0, 30, 20, False))

    assert _coincidences(sketch) == [
        (0, _END, 1, _START),
        (1, _END, 2, _START),
        (2, _END, 3, _START),
        (3, _END, 0, _START),
    ]


def test_a_polygon_is_closed():
    sketch = _run(
        lambda c: run_sketch_add_regular_polygon(c, "Doc", "Sketch", 0, 0, 10, 5, 0, False)
    )

    assert len(_coincidences(sketch)) == 5
    assert _coincidences(sketch)[-1] == (4, _END, 0, _START)


@pytest.mark.parametrize("closed, expected", [(False, 1), (True, 3)])
def test_a_polyline_joins_its_segments(closed, expected):
    sketch = _run(
        lambda c: run_sketch_add_polyline(
            c, "Doc", "Sketch", [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}], closed, False
        )
    )

    assert len(_coincidences(sketch)) == expected
