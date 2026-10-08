"""set_color takes channels and transparency in 0.0-1.0 and must reject the rest.

r=5, g=-2, transparency=-3 used to be "applied": FreeCAD clamped or wrapped the
values silently, so the caller got a colour it never asked for.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_color import (
    build_set_color_request,
)

pytestmark = pytest.mark.unit


def _build(**overrides):
    args = {"doc_name": "Doc", "obj_name": "Box", "r": 0.2, "g": 0.4, "b": 0.6,
            "transparency": 0.5}
    args.update(overrides)
    return build_set_color_request(**args)


@pytest.mark.parametrize("value", [0, 0.0, 0.5, 1, 1.0])
@pytest.mark.parametrize("field", ["r", "g", "b", "transparency"])
def test_values_in_unit_range_are_accepted(field, value):
    assert not isinstance(_build(**{field: value}), dict)


@pytest.mark.parametrize("value", [-0.01, 1.01, 5, -3, float("nan"), float("inf")])
@pytest.mark.parametrize("field", ["r", "g", "b", "transparency"])
def test_values_outside_unit_range_are_rejected(field, value):
    failure = _build(**{field: value})

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert field in failure["error"]
