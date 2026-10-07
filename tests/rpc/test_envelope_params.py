"""invoke_v2 parameter binding must reject mismatches with a public reason."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP._shared.protocol.protocol_error import ProtocolError
from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.envelope_params import (
    ordered_envelope_params,
)

pytestmark = pytest.mark.unit


def _target(doc_name, operation_id=None):
    return doc_name, operation_id


def test_matching_params_bind_in_signature_order() -> None:
    assert ordered_envelope_params(_target, {"operation_id": "op", "doc_name": "D"}) == (
        "D",
        "op",
    )


@pytest.mark.parametrize(
    "params",
    [{"doc_selector": {"document_name": "D"}}, {"doc_name": "D", "unknown": 1}, {}],
)
def test_mismatched_params_are_an_invalid_method_params_protocol_error(params) -> None:
    with pytest.raises(ProtocolError) as raised:
        ordered_envelope_params(_target, params)

    assert raised.value.code == "INVALID_METHOD_PARAMS"
