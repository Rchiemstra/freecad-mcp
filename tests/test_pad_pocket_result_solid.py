"""D-27: pad/pocket must not commit a result without a real solid.

The postcondition only checked ``Shape.isNull()``. Natively a pocket that removed the
whole body committed with 0 solids / volume 0, and a pad of two overlapping rectangles
committed a single solid of volume -0.0, both as ``outcome: committed``. A result must
contain at least one solid and have a positive volume, or the commit is rolled back.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature import (
    PadFeatureReceipt,
    read_pad_feature_result,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature_mutation import PadFeatureError
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature import (
    PocketFeatureReceipt,
    read_pocket_feature_result,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature_mutation import (
    PocketFeatureError,
)

pytestmark = pytest.mark.unit


class _Shape:
    def __init__(self, solids: int, volume: float) -> None:
        self.Solids = [object()] * solids
        self.Volume = volume

    def isNull(self) -> bool:
        return False


def _document(type_id: str, shape: _Shape) -> tuple[SimpleNamespace, SimpleNamespace]:
    sketch = SimpleNamespace(Name="Sk")
    feature = SimpleNamespace(
        Name="F", Label="F", TypeId=type_id, Profile=[sketch, [""]], Length=5.0, Shape=shape
    )
    body = SimpleNamespace(Name="Body", Group=[sketch, feature], Tip=feature)
    objects = {"F": feature, "Body": body, "Sk": sketch}
    return SimpleNamespace(getObject=objects.get), feature


# (solids, volume) exactly as observed natively, plus a healthy control.
_DEGENERATE = [pytest.param(0, 0.0, id="no-solid-volume-0"), pytest.param(1, -0.0, id="one-solid-volume-minus-0")]


@pytest.mark.parametrize(("solids", "volume"), _DEGENERATE)
def test_pad_rejects_a_result_without_a_real_solid(solids: int, volume: float) -> None:
    doc, pad = _document("PartDesign::Pad", _Shape(solids, volume))
    receipt = PadFeatureReceipt(name="F", pad=pad, body_name="Body", sketch_name="Sk", expected_length=5.0)

    with pytest.raises(PadFeatureError) as caught:
        read_pad_feature_result(doc, receipt)
    assert caught.value.code == "PAD_SHAPE_EMPTY"


@pytest.mark.parametrize(("solids", "volume"), _DEGENERATE)
def test_pocket_rejects_a_result_without_a_real_solid(solids: int, volume: float) -> None:
    doc, pocket = _document("PartDesign::Pocket", _Shape(solids, volume))
    receipt = PocketFeatureReceipt(
        name="F", pocket=pocket, body_name="Body", sketch_name="Sk", expected_length=5.0
    )

    with pytest.raises(PocketFeatureError) as caught:
        read_pocket_feature_result(doc, receipt)
    assert caught.value.code == "POCKET_SHAPE_EMPTY"


def test_healthy_results_still_pass() -> None:
    doc, pad = _document("PartDesign::Pad", _Shape(1, 16000.0))
    read_pad_feature_result(
        doc, PadFeatureReceipt(name="F", pad=pad, body_name="Body", sketch_name="Sk", expected_length=5.0)
    )
    doc, pocket = _document("PartDesign::Pocket", _Shape(1, 15000.0))
    read_pocket_feature_result(
        doc,
        PocketFeatureReceipt(name="F", pocket=pocket, body_name="Body", sketch_name="Sk", expected_length=5.0),
    )
