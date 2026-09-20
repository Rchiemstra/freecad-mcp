"""Unit coverage for the typed ``get_object`` query slice."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_object import (
    run_get_object,
)
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


def test_get_object_observed_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)

    result = run_get_object(collab, "Doc", "Box")

    assert result["success"] is True
    assert result["outcome"] == "observed"
    assert result["object"] == "Box"
    assert result["object_data"]["Name"] == "Box"
    assert "commit" not in events


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_get_object(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_document_nameerror_is_document_not_found():
    events: list[str] = []

    def _raise_name_error(_name: str):
        raise NameError("stale document handle")

    app = type(
        "App",
        (),
        {"getDocument": staticmethod(_raise_name_error)},
    )()
    collab, _api = collaborators(FakeDocument(events), events)
    collab.freecad = app

    result = run_get_object(collab, "StaleDoc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_missing_object_is_rejected():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_get_object(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "OBJECT_NOT_FOUND"


def test_falsy_document_is_not_treated_as_missing_object():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)
    collab.freecad = type(
        "App",
        (),
        {"getDocument": staticmethod(lambda _name: "")},
    )()

    result = run_get_object(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_duplicate_label_resolves_by_name_only():
    events: list[str] = []
    document = FakeDocument(events)
    first = FakeObject("BoxA")
    first.Label = "SharedLabel"
    second = FakeObject("BoxB")
    second.Label = "SharedLabel"
    document.objects["BoxA"] = first
    document.objects["BoxB"] = second
    collab, _api = collaborators(document, events)

    by_name = run_get_object(collab, "Doc", "BoxA")
    by_label = run_get_object(collab, "Doc", "SharedLabel")

    assert by_name["success"] is True
    assert by_name["object"] == "BoxA"
    assert by_label["success"] is False
    assert by_label["error_code"] == "OBJECT_NOT_FOUND"


def test_serialize_failure_is_structured():
    events: list[str] = []
    document = FakeDocument(events)
    document.objects["Box"] = FakeObject("Box")
    collab, _api = collaborators(document, events)

    def _boom(_obj: object) -> dict[str, object]:
        raise RuntimeError("serialization exploded")

    collab.serialize_object = _boom

    result = run_get_object(collab, "Doc", "Box")

    assert result["success"] is False
    assert result["error_code"] == "GET_OBJECT_SERIALIZE_FAILED"
