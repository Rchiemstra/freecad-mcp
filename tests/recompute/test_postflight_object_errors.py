"""Postflight validation reports each failing object's own error text."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import (
    validate_document_invariants,
)

pytestmark = pytest.mark.unit

_BINDING = "Document 'QASrc' not found in 'QASrc' in property binding 'QADst#Box.Length'"


def test_a_valid_document_passes_postflight():
    box = SimpleNamespace(Name="Box", State=[], TypeId="Part::Box")
    result = validate_document_invariants(SimpleNamespace(Objects=[box]))
    assert result["ok"] is True


def test_a_bad_tip_is_named():
    body = SimpleNamespace(
        Name="Body",
        State=[],
        TypeId="PartDesign::Body",
        Group=(),
        Tip=object(),
        isDerivedFrom=lambda kind: kind == "PartDesign::Body",
    )
    with pytest.raises(RuntimeError, match=r"Body\.Tip"):
        validate_document_invariants(SimpleNamespace(Objects=[body]))


def test_postflight_includes_the_object_error_text():
    box = SimpleNamespace(
        Name="Box",
        State=["Invalid"],
        TypeId="Part::Box",
        getStatusString=lambda: _BINDING,
    )
    with pytest.raises(RuntimeError, match="QASrc") as caught:
        validate_document_invariants(SimpleNamespace(Objects=[box]))
    text = str(caught.value)
    assert "QADst#Box.Length" in text
    assert "Box" in text


def test_postflight_reads_the_document_error_description():
    box = SimpleNamespace(
        Name="Box",
        State=["Error"],
        TypeId="Part::Box",
        getStatusString=lambda: "Error",
        Document=SimpleNamespace(getErrorDescription=lambda _obj: _BINDING),
    )
    with pytest.raises(RuntimeError, match="property binding") as caught:
        validate_document_invariants(SimpleNamespace(Objects=[box]))
    assert "Box:" in str(caught.value)
