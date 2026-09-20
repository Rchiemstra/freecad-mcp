"""D-03: revolve ``symmetric`` must map onto ``SideType`` on FreeCAD builds without ``Symmetric``.

FreeCAD 26.3 ``PartDesign::Revolution`` exposes ``SideType`` (One side / Two sides / Symmetric)
instead of a ``Symmetric`` boolean. The typed handler only knew the boolean, so
``revolve_feature(symmetric=true)`` failed with "does not support any of: Symmetric".
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.feature_mutate_support import (
    set_revolution_symmetric,
)

pytestmark = pytest.mark.unit


class _Revolution:
    """FreeCAD 26.3 shape: SideType enum, no Symmetric/Midplane."""

    PropertiesList = ["Angle", "Profile", "ReferenceAxis", "Reversed", "SideType", "Type"]

    def __init__(self) -> None:
        self.SideType = "One side"


class _LegacyRevolution:
    PropertiesList = ["Angle", "Profile", "ReferenceAxis", "Reversed", "Symmetric"]

    def __init__(self) -> None:
        self.Symmetric = False


def test_symmetric_true_uses_side_type():
    feature = _Revolution()
    assert set_revolution_symmetric(feature, True) == "SideType"
    assert feature.SideType == "Symmetric"


def test_symmetric_false_keeps_one_side():
    feature = _Revolution()
    assert set_revolution_symmetric(feature, False) == "SideType"
    assert feature.SideType == "One side"


def test_legacy_symmetric_boolean_still_supported():
    feature = _LegacyRevolution()
    assert set_revolution_symmetric(feature, True) == "Symmetric"
    assert feature.Symmetric is True


def test_unsupported_symmetric_request_is_refused():
    class _Bare:
        PropertiesList = ["Angle"]

    with pytest.raises(RuntimeError):
        set_revolution_symmetric(_Bare(), True)
    assert set_revolution_symmetric(_Bare(), False) is None
