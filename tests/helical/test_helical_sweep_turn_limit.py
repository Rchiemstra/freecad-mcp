"""helical_sweep_feature must refuse helices FreeCAD cannot sweep in time.

pitch=0.01, height=100000 asked for ten million turns: FreeCAD swept for
minutes at full CPU, the GUI stopped answering and every later MCP call
failed. In a debug build 150 turns sweep in under a second, 200 take over a
minute and 250 over three minutes.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.helical_sweep_feature import (
    build_helical_sweep_feature_request,
)

pytestmark = pytest.mark.unit


def _build(pitch, height):
    return build_helical_sweep_feature_request("Doc", "Prof", "Helix", pitch, height, 20)


@pytest.mark.parametrize("pitch, height", [(3, 30), (1, 150), (0.5, 75)])
def test_helices_up_to_the_limit_are_accepted(pitch, height):
    request = _build(pitch, height)

    assert not isinstance(request, dict)


@pytest.mark.parametrize("pitch, height", [(0.01, 100000), (1, 151), (0.1, 20)])
def test_helices_beyond_the_limit_are_rejected(pitch, height):
    failure = _build(pitch, height)

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert "at most 150 turns" in failure["error"]
