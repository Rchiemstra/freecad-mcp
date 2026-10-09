"""Operations on two inputs must get two different inputs.

boolean_union(CylA, CylA) made FreeCAD's tree warn "duplicate child item
PartLab#SelfFuse.CylA"; sweep_feature with the profile as its own path failed
with "A fatal error occurred when making the pipe".
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_difference import (
    build_boolean_difference_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_intersection import (
    build_boolean_intersection_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.boolean_union import (
    build_boolean_union_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.loft_feature import (
    build_loft_feature_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sweep_feature import (
    build_sweep_feature_request,
)

pytestmark = pytest.mark.unit

_BUILDS = {
    "union": lambda a, b: build_boolean_union_request("Doc", a, b, "Out"),
    "difference": lambda a, b: build_boolean_difference_request("Doc", a, b, "Out"),
    "intersection": lambda a, b: build_boolean_intersection_request("Doc", a, b, "Out"),
    "sweep": lambda a, b: build_sweep_feature_request("Doc", a, b, "Sweep"),
    "loft": lambda a, b: build_loft_feature_request("Doc", [a, b], "Loft"),
}


@pytest.mark.parametrize("kind", sorted(_BUILDS))
def test_the_same_object_twice_is_rejected(kind):
    failure = _BUILDS[kind]("CylA", "CylA")

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert "'CylA'" in failure["error"]


@pytest.mark.parametrize("kind", sorted(_BUILDS))
def test_two_different_objects_are_accepted(kind):
    request = _BUILDS[kind]("CylA", "CylB")

    assert not isinstance(request, dict)
