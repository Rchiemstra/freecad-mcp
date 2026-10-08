"""validate_geometry must report a null shape instead of leaking OCC errors.

A PartDesign Body without a Tip has a null Shape. Reading Volume or Area from it
raised ``Standard_NullObject`` and the tool failed with
"19Standard_NullObject BRepCheck_Analyzer::Init() - NULL shape".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions

pytestmark = pytest.mark.unit


class _NullShape:
    ShapeType = "Compound"

    def isNull(self) -> bool:
        return True

    def __getattr__(self, name: str):
        raise RuntimeError("19Standard_NullObject BRepCheck_Analyzer::Init() - NULL shape")


class _Document:
    def __init__(self, obj: object) -> None:
        self._obj = obj

    def getObject(self, name: str) -> object | None:
        return self._obj if name == self._obj.Name else None


def test_null_shape_is_reported_as_invalid_geometry():
    body = SimpleNamespace(Name="Body", Label="Body", Shape=_NullShape())

    result = measure_io_actions.validate_geometry(_Document(body), "Body")

    assert result["is_null"] is True
    assert result["is_valid"] is False
    assert result["check_ok"] is False
    assert result["check_errors"] == ["shape is null"]
    assert result["volume_mm3"] == 0.0
    assert result["face_count"] == 0
