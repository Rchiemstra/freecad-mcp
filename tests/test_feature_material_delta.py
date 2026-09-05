from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.features_gui import (
    _build_feature_result,
    _material_baseline,
)

pytestmark = pytest.mark.unit


class Shape:
    def __init__(self, volume: float):
        self.Volume = volume
        self.Solids = [object()]
        self.BoundBox = SimpleNamespace(
            XMin=0.0,
            YMin=0.0,
            ZMin=0.0,
            XMax=1.0,
            YMax=1.0,
            ZMax=1.0,
        )

    def isNull(self):
        return False


def _feature_result(*, before: float, after: float, operation: str):
    source = SimpleNamespace(Name="Base", Shape=Shape(before))
    sketch = SimpleNamespace(Name="Sketch")
    feature = SimpleNamespace(Name="Feature", Shape=Shape(after), State=[])
    body = SimpleNamespace(Name="Body", Group=[source, sketch, feature], Tip=feature)
    document = SimpleNamespace(Name="Model")
    return _build_feature_result(
        document,
        body,
        sketch,
        feature,
        {},
        operation=operation,
        source_feature=source.Name,
        volume_before=before,
    )


def test_material_baseline_uses_last_solid_before_the_profile():
    base = SimpleNamespace(Name="Base", Shape=Shape(100.0))
    sketch = SimpleNamespace(Name="Sketch")
    body = SimpleNamespace(Group=[base, sketch])

    assert _material_baseline(body, sketch) == ("Base", 100.0)


@pytest.mark.parametrize("operation", ["additive", "subtractive"])
def test_zero_material_feature_is_rejected(operation):
    result = _feature_result(before=100.0, after=100.0, operation=operation)

    assert result["success"] is False
    assert result["ok"] is False
    assert result["error_code"] == "ZERO_MATERIAL_DELTA"
    assert result["volume_before_mm3"] == 100.0
    assert result["volume_after_mm3"] == 100.0
    assert result["material_delta_mm3"] == 0.0


@pytest.mark.parametrize(
    ("operation", "after", "expected_delta"),
    [("additive", 125.0, 25.0), ("subtractive", 75.0, -25.0)],
)
def test_material_changing_feature_reports_signed_delta(
    operation, after, expected_delta
):
    result = _feature_result(before=100.0, after=after, operation=operation)

    assert result["success"] is True
    assert result["material_delta_mm3"] == expected_delta
    assert result["source_feature"] == "Base"


@pytest.mark.parametrize(
    ("operation", "after"),
    [("additive", 75.0), ("subtractive", 125.0)],
)
def test_material_direction_mismatch_is_rejected(operation, after):
    result = _feature_result(before=100.0, after=after, operation=operation)

    assert result["success"] is False
    assert result["error_code"] == "MATERIAL_DELTA_DIRECTION_MISMATCH"
