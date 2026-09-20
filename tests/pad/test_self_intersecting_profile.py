"""D-07: pad/pocket must refuse a self-intersecting (bow-tie) closed profile.

The bow-tie wire (-6,-6)->(6,6)->(6,-6)->(-6,6)->close is closed, so the closed-wire
pre-check passed and PartDesign silently built two triangular prisms. OCCT reports a face on
that wire as invalid (verified with FreeCADCmd: ``Part.Face(bowtie).isValid() is False``).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import pad_feature, pocket_feature
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature_mutation import PadFeatureError
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature_mutation import (
    PocketFeatureError,
)

pytestmark = pytest.mark.unit


class _Wire:
    def __init__(self, *, closed: bool, self_intersecting: bool) -> None:
        self._closed = closed
        self.self_intersecting = self_intersecting

    def isClosed(self) -> bool:
        return self._closed


class _Face:
    def __init__(self, wire: _Wire) -> None:
        self._wire = wire

    def isValid(self) -> bool:
        return not self._wire.self_intersecting


PART = SimpleNamespace(Face=_Face)


def _sketch(*wires: _Wire) -> SimpleNamespace:
    shape = SimpleNamespace(isClosed=lambda: True, Wires=list(wires))
    return SimpleNamespace(ConflictingConstraints=[], MalformedConstraints=[], Shape=shape)


CASES = [
    (pad_feature._require_closed_profile, PadFeatureError),
    (pocket_feature._require_closed_profile, PocketFeatureError),
]


@pytest.mark.parametrize(("check", "error"), CASES)
def test_bowtie_profile_is_refused(check, error) -> None:
    sketch = _sketch(_Wire(closed=True, self_intersecting=True))
    with pytest.raises(error) as caught:
        check(sketch, "Bowtie", part=PART)
    assert caught.value.code == "SKETCH_PROFILE_SELF_INTERSECTING"


@pytest.mark.parametrize(("check", "error"), CASES)
def test_simple_profile_with_hole_is_accepted(check, error) -> None:
    sketch = _sketch(
        _Wire(closed=True, self_intersecting=False),
        _Wire(closed=True, self_intersecting=False),
    )
    check(sketch, "PlateWithHole", part=PART)


@pytest.mark.parametrize(("check", "error"), CASES)
def test_check_is_skipped_without_part_module(check, error) -> None:
    sketch = _sketch(_Wire(closed=True, self_intersecting=True))
    check(sketch, "Bowtie")
