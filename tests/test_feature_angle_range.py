"""Polar pattern and revolve angles must stay within FreeCAD's 360 degrees.

FreeCAD's PropertyAngle silently clamps to [-360, 360]: ``angle=720`` on
``polar_pattern_feature`` and ``angle=1000`` on ``revolve_feature`` were
reported as successes while the features were built with 360 degrees.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.polar_pattern_feature import (
    build_polar_pattern_feature_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.revolve_feature import (
    build_revolve_feature_request,
)

pytestmark = pytest.mark.unit


def _polar(angle):
    return build_polar_pattern_feature_request("Doc", "Pad", "Polar", 6, angle)


def _revolve(angle):
    return build_revolve_feature_request("Doc", "Sketch", "Revolve", angle)


@pytest.mark.parametrize("build", [_polar, _revolve])
@pytest.mark.parametrize("angle", [0.5, 90, 359.999, 360])
def test_angles_up_to_a_full_turn_are_accepted(build, angle):
    request = build(angle)

    assert not isinstance(request, dict)
    assert request.angle == float(angle)


@pytest.mark.parametrize("build", [_polar, _revolve])
@pytest.mark.parametrize("angle", [360.001, 720, 1000])
def test_angles_beyond_a_full_turn_are_rejected(build, angle):
    failure = build(angle)

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert "angle must be <= 360" in failure["error"]
