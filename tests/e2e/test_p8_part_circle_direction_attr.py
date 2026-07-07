"""P8: `Part.Circle` prints `Direction` in its str() but the API attribute is
`Axis` (no `Direction`/`Normal`). The string representation and the attribute
API should agree; accessing `crv.Direction` raises AttributeError.
"""
from __future__ import annotations

import pytest

Part = pytest.importorskip("Part")

pytestmark = [
    pytest.mark.core,
    pytest.mark.xfail(
        strict=True,
        reason="FreeCAD: Part.Circle str() prints Direction but the API uses Axis (P8)",
    ),
]


def test_part_circle_has_direction_and_normal_aliases():
    FreeCAD = __import__("FreeCAD")
    c = Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 1.5)
    # Axis is the canonical attribute; Direction/Normal must work as aliases so
    # that str(c) (which prints "Direction") and the attribute API agree.
    assert hasattr(c, "Axis")
    assert hasattr(c, "Direction") or hasattr(c, "Normal"), (
        "Part.Circle exposes neither Direction nor Normal; str() prints Direction but the API is Axis"
    )
    alias = getattr(c, "Direction", None)
    if alias is None:
        alias = getattr(c, "Normal")
    assert (round(alias.x, 9), round(alias.y, 9), round(alias.z, 9)) == (
        round(c.Axis.x, 9), round(c.Axis.y, 9), round(c.Axis.z, 9),
    ), f"Direction/Normal alias {alias} disagrees with Axis {c.Axis}"
