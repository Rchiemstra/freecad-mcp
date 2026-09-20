"""D-08: pad/pocket ``length`` must be a positive, finite number.

A negative length used to be silently reinterpreted as a reversed pad; the tool has an
explicit ``reversed_dir`` for that intent. NaN and infinity pass a plain ``<= 0`` check.
"""

from __future__ import annotations

import math

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature import build_pad_feature_request
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature import (
    build_pocket_feature_request,
)

pytestmark = pytest.mark.unit

BUILDERS = {
    "pad": lambda length: build_pad_feature_request("Doc", "Sketch", "Pad", length, None, False, False),
    "pocket": lambda length: build_pocket_feature_request(
        "Doc", "Sketch", "Pocket", length, None, False, False
    ),
}


@pytest.mark.parametrize("kind", sorted(BUILDERS))
@pytest.mark.parametrize("length", [-10, -0.001, 0, 0.0, math.nan, math.inf, -math.inf])
def test_out_of_contract_length_is_rejected(kind: str, length: float) -> None:
    result = BUILDERS[kind](length)
    assert isinstance(result, dict), f"{kind} accepted length={length!r}"
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("kind", sorted(BUILDERS))
def test_positive_length_is_accepted(kind: str) -> None:
    result = BUILDERS[kind](12.5)
    assert not isinstance(result, dict)
    assert result.length == 12.5
