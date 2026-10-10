"""A lost authenticated outcome must name the request the caller can poll."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.v2_methods_ops.invoke_v2_dispatch import (
    uncertain_outcome_message,
)
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.operations.parametric_ops.linear_pattern_feature import (
    linear_pattern_feature_operation,
)

pytestmark = pytest.mark.unit

_REQUEST_ID = "11111111-2222-4333-8444-555555555555"


def test_uncertain_outcome_message_names_get_request_status():
    message = uncertain_outcome_message(_REQUEST_ID)

    assert "outcome is uncertain" in message
    assert f"request_id={_REQUEST_ID}" in message
    assert "get_request_status" in message
    blank = uncertain_outcome_message("  ")
    assert "request_id=unknown" in blank


def test_tool_failure_keeps_the_request_id_in_the_structured_result():
    message = uncertain_outcome_message(_REQUEST_ID)

    def raise_uncertain(*_args, **_kwargs):
        raise JsonRpcRemoteError(
            -32000,
            message,
            data={"error_code": "REQUEST_OUTCOME_UNCERTAIN", "request_id": _REQUEST_ID},
        )

    response = linear_pattern_feature_operation(
        SimpleNamespace(linear_pattern_feature=raise_uncertain),
        True,
        "Doc",
        "Pocket",
        "Array",
        40.0,
        5,
    )

    text = " ".join(getattr(item, "text", "") for item in response.content)
    envelope = response.structuredContent
    assert response.isError
    assert "get_request_status" in text
    assert f"request_id={_REQUEST_ID}" in text
    assert envelope["request_id"] == _REQUEST_ID
    assert envelope["data"]["request_id"] == _REQUEST_ID
    assert "LINEAR_PATTERN_FEATURE_TRANSPORT_UNCERTAIN" in str(envelope.get("error_code"))
