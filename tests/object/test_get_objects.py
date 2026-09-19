"""Unit coverage for the typed ``get_objects`` query slice."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from addon.FreeCADMCP._shared.protocol.get_objects_contract import (
    MAX_PAGE_PAYLOAD_BYTES,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import assembly_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_document_tree import (
    run_get_document_tree,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_objects import (
    run_get_objects,
)
from addon.FreeCADMCP.rpc_server.serialize import project_listing_object
from tests.typed_rpc_fakes import FakeDocument, FakeObject, collaborators

pytestmark = pytest.mark.unit


class _HugeShape:
    def __repr__(self) -> str:
        return "x" * 10_000

    @property
    def Volume(self) -> float:
        return 1.0

    @property
    def Area(self) -> float:
        return 1.0

    @property
    def Vertexes(self) -> list[object]:
        return []

    @property
    def Edges(self) -> list[object]:
        return []

    @property
    def Faces(self) -> list[object]:
        return []


class _FakeView:
    def __init__(self) -> None:
        self.ShapeColor = (0.8, 0.8, 0.8)
        self.Transparency = 0
        self.Visibility = True


def _document_with_objects(count: int, *, huge_shape: bool = False) -> FakeDocument:
    events: list[str] = []
    document = FakeDocument(events)
    for index in range(count):
        name = f"Obj{index:03d}"
        obj = FakeObject(name)
        if huge_shape:
            obj.Shape = _HugeShape()
            obj.ViewObject = _FakeView()
            obj.PropertiesList = ["Label", "Length"]
            obj.Length = 12.5
        document.objects[name] = obj
    return document


def test_baseline_contract_envelope_not_raw_list():
    """Fails while get_objects returns a bare JSON array instead of the v1 envelope."""
    events: list[str] = []
    document = _document_with_objects(3)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc")

    assert isinstance(result, dict)
    assert result.get("contract_version") == 1
    assert result.get("outcome") == "observed"
    assert "objects" in result
    assert not isinstance(result, list)


def test_missing_document_is_rejected_not_empty_list():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_get_objects(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert result["outcome"] == "rejected"


def test_empty_document_success():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc")

    assert result["success"] is True
    assert result["total_count"] == 0
    assert result["objects"] == []
    assert result["complete"] is True
    assert result["next_cursor"] is None


def test_ten_objects_default_projection_is_compact():
    events: list[str] = []
    document = _document_with_objects(10, huge_shape=True)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc")

    assert result["success"] is True
    assert result["total_count"] == 10
    assert result["returned_count"] == 10
    assert result["complete"] is True
    assert result["next_cursor"] is None
    payload = json.dumps(result)
    assert len(payload) < 4 * 1024
    for row in result["objects"]:
        assert set(row) <= {"Name", "Label", "TypeId"}
        assert "Properties" not in row
        assert "Shape" not in row
        assert "ViewObject" not in row
        assert "x" * 100 not in payload


def test_hundred_objects_paginates_in_name_order():
    events: list[str] = []
    document = _document_with_objects(100)
    collab, _api = collaborators(document, events)

    page1 = run_get_objects(collab, "Doc", page_size=50)
    assert page1["total_count"] == 100
    assert page1["returned_count"] == 50
    assert page1["complete"] is False
    assert page1["next_cursor"] is not None

    page2 = run_get_objects(collab, "Doc", page_size=50, cursor=page1["next_cursor"])
    assert page2["snapshot_id"] == page1["snapshot_id"]
    assert page2["total_count"] == 100
    assert page2["returned_count"] == 50
    assert page2["complete"] is True
    assert page2["next_cursor"] is None

    page1_names = [row["Name"] for row in page1["objects"]]
    page2_names = [row["Name"] for row in page2["objects"]]
    names = page1_names + page2_names
    assert names == sorted(names)
    assert len(names) == len(set(names)) == 100


def test_projections_and_invalid_page_size():
    events: list[str] = []
    document = _document_with_objects(1, huge_shape=True)
    collab, _api = collaborators(document, events)

    projected = run_get_objects(
        collab,
        "Doc",
        fields=["Name", "TypeId"],
        include_shape=True,
        include_view=True,
        include_properties=["Length"],
    )
    row = projected["objects"][0]
    assert "Label" not in row
    assert set(row["Shape"]) == {
        "Volume",
        "Area",
        "VertexCount",
        "EdgeCount",
        "FaceCount",
    }
    assert set(row["ViewObject"]) == {"ShapeColor", "Transparency", "Visibility"}
    assert row["Properties"] == {"Length": 12.5}

    invalid = run_get_objects(collab, "Doc", page_size=0)
    assert invalid["error_code"] == "INVALID_ARGUMENT"


def test_serialize_failure_yields_row_stub():
    events: list[str] = []
    document = _document_with_objects(2)
    collab, _api = collaborators(document, events)

    def _project(obj, **kwargs):
        if getattr(obj, "Name", "") == "Obj001":
            raise RuntimeError("serialization exploded")
        return project_listing_object(obj, **kwargs)

    with patch(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_objects.project_listing_object",
        side_effect=_project,
    ):
        result = run_get_objects(collab, "Doc")

    assert result["total_count"] == 2
    assert result["complete"] is True
    assert any("error" in row for row in result["objects"])


def test_fifty_objects_single_complete_page():
    events: list[str] = []
    document = _document_with_objects(50)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc", page_size=50)

    assert result["success"] is True
    assert result["total_count"] == 50
    assert result["returned_count"] == 50
    assert result["complete"] is True
    assert result["next_cursor"] is None


def test_two_hundred_fifty_objects_five_pages():
    events: list[str] = []
    document = _document_with_objects(250)
    collab, _api = collaborators(document, events)

    all_names: list[str] = []
    cursor = None
    for page_index in range(5):
        kwargs: dict[str, object] = {"page_size": 50}
        if cursor is not None:
            kwargs["cursor"] = cursor
        page = run_get_objects(collab, "Doc", **kwargs)
        assert page["success"] is True
        assert page["returned_count"] == 50
        if page_index < 4:
            assert page["complete"] is False
            assert page["next_cursor"] is not None
        else:
            assert page["complete"] is True
            assert page["next_cursor"] is None
        all_names.extend(row["Name"] for row in page["objects"])
        cursor = page["next_cursor"]

    assert len(all_names) == 250
    assert len(set(all_names)) == 250


def test_two_hundred_fifty_objects_single_page_under_payload_cap():
    events: list[str] = []
    document = _document_with_objects(250)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc", page_size=250)

    assert result["success"] is True
    assert result["total_count"] == 250
    assert result["returned_count"] == 250
    assert result["complete"] is True
    assert len(json.dumps(result)) < MAX_PAGE_PAYLOAD_BYTES


def test_stale_cursor_after_membership_change():
    events: list[str] = []
    document = _document_with_objects(100)
    collab, _api = collaborators(document, events)

    page1 = run_get_objects(collab, "Doc", page_size=50)
    document.objects["Inserted"] = FakeObject("Inserted")

    stale = run_get_objects(collab, "Doc", page_size=50, cursor=page1["next_cursor"])

    assert stale["success"] is False
    assert stale["error_code"] == "STALE_CURSOR"
    assert stale["retry_safe"] is True


def test_invalid_cursor_rejected():
    events: list[str] = []
    document = _document_with_objects(3)
    collab, _api = collaborators(document, events)

    invalid = run_get_objects(collab, "Doc", cursor="not-a-valid-cursor")
    assert invalid["error_code"] == "INVALID_CURSOR"

    empty = run_get_objects(collab, "Doc", cursor="")
    assert empty["error_code"] == "INVALID_ARGUMENT"


def test_unknown_field_rejected():
    events: list[str] = []
    document = _document_with_objects(1)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "Doc", fields=["Name", "MissingField"])

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_invalid_page_sizes_rejected():
    events: list[str] = []
    document = _document_with_objects(1)
    collab, _api = collaborators(document, events)

    for page_size in (0, -1, 251):
        result = run_get_objects(collab, "Doc", page_size=page_size)
        assert result["success"] is False
        assert result["error_code"] == "INVALID_ARGUMENT"


def test_empty_doc_name_rejected():
    events: list[str] = []
    document = _document_with_objects(1)
    collab, _api = collaborators(document, events)

    result = run_get_objects(collab, "   ")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_payload_too_large_not_truncated():
    events: list[str] = []
    document = _document_with_objects(10, huge_shape=True)
    collab, _api = collaborators(document, events)

    with patch(
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_objects.MAX_PAGE_PAYLOAD_BYTES",
        256,
    ):
        result = run_get_objects(
            collab,
            "Doc",
            include_shape=True,
            include_view=True,
            include_properties=["Length"],
        )

    assert result["success"] is False
    assert result["error_code"] == "PAYLOAD_TOO_LARGE"
    assert result["retry_safe"] is False


def _assert_listing_rows_compact(rows: list[dict[str, object]], payload: str) -> None:
    for row in rows:
        assert set(row) <= {"Name", "Label", "TypeId"}
        assert "Properties" not in row
        assert "Shape" not in row
        assert "ViewObject" not in row
    assert "x" * 100 not in payload


def _assert_tree_nodes_compact(nodes: list[dict[str, object]], payload: str) -> None:
    for node in nodes:
        assert "Properties" not in node
        assert "Shape" not in node
        assert "ViewObject" not in node
    assert "x" * 100 not in payload


def test_get_objects_default_projection_compact_vs_document_tree():
    for count in (10, 250):
        events: list[str] = []
        document = _document_with_objects(count, huge_shape=True)
        collab, _api = collaborators(document, events)

        objects_result = run_get_objects(collab, "Doc")
        objects_payload = json.dumps(objects_result)
        _assert_listing_rows_compact(objects_result["objects"], objects_payload)

        with patch.object(
            assembly_io_actions,
            "get_document_tree",
            wraps=assembly_io_actions.get_document_tree,
        ):
            tree_result = run_get_document_tree(collab, "Doc")
        tree_payload = json.dumps(tree_result)
        _assert_tree_nodes_compact(tree_result["roots"], tree_payload)

        if count == 250:
            assert objects_result["returned_count"] == 50
            assert tree_result["roots"]
            assert len(tree_result["roots"]) == 250
