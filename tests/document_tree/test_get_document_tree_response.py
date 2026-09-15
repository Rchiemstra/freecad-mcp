"""Adversarial wire cases for the get_document_tree contract."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.get_document_tree_contract import (
    make_get_document_tree_failure,
    make_get_document_tree_success,
    make_get_document_tree_uncertain,
    parse_get_document_tree_response,
)
from freecad_mcp.operations.parametric_ops.get_document_tree import get_document_tree_operation


def _success():
    return make_get_document_tree_success(doc_name="Doc", root_filter="", max_depth=4, roots=[])


@pytest.mark.parametrize("raw", [None, [], 1, "timeout", {}, {1: "bad key"}])
def test_unknown_response_never_proves_rejection(raw):
    result = parse_get_document_tree_response(raw)
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
    assert result["committed"] is None
    assert result["retry_safe"] is False


def test_valid_success_round_trips():
    raw = _success()
    assert parse_get_document_tree_response(raw) == raw


def test_transport_failure_preserves_unknown_model_state():
    def lost_response(*_args, **_kwargs):
        raise TimeoutError("response lost after request was sent")

    response = get_document_tree_operation(SimpleNamespace(get_document_tree=lost_response), "Doc")
    assert response.isError is True
    data = response.structuredContent["data"]
    assert data["error_code"] == "GET_DOCUMENT_TREE_TRANSPORT_UNCERTAIN"
    assert data["outcome"] == "uncertain"
    assert data["retry_safe"] is False


def test_contradictory_success_cannot_escape():
    result = parse_get_document_tree_response(dict(_success(), rollback_failed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
