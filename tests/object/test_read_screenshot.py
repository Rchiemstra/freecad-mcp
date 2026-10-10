"""A failed screenshot must not discard a read that already has its data."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.get_object_contract import make_get_object_success
from freecad_mcp._shared.protocol.get_objects_contract import make_get_objects_success
from freecad_mcp._shared.protocol.json_rpc_client import JsonRpcRemoteError
from freecad_mcp.operations.core_ops.execute_ops import execute_code_operation
from freecad_mcp.operations.core_ops.object_ops import (
    get_object_operation,
    get_objects_operation,
)

pytestmark = pytest.mark.unit

_BLANK = "screenshot render produced a near-blank image"
_BOUNDS = "personal view focus has no renderable bounds"


def _remote(message: str) -> JsonRpcRemoteError:
    return JsonRpcRemoteError(-32000, message)


def _objects_page(objects: list[dict[str, object]]):
    return make_get_objects_success(
        doc_name="Doc",
        objects=objects,
        total_count=len(objects),
        returned_count=len(objects),
        page_size=10,
        complete=True,
        next_cursor=None,
        snapshot_id="snap",
    )


def test_get_object_keeps_its_screenshot_when_the_view_renders():
    freecad = MagicMock()
    freecad.get_object.return_value = make_get_object_success(
        "Box", {"Name": "Box", "Length": 10}
    )
    freecad.get_active_screenshot.return_value = "png"

    response = get_object_operation(freecad, False, "Doc", "Box")

    assert response.isError is False
    assert '"Length": 10' in response.content[0].text or '"Length":10' in response.content[0].text
    assert response.content[1].data == "png"
    assert "screenshot_warning" not in response.structuredContent["data"]


def test_get_objects_returns_the_page_with_its_screenshot():
    freecad = MagicMock()
    freecad.get_objects.return_value = _objects_page([{"Name": "Box"}])
    freecad.get_active_screenshot.return_value = "png"

    response = get_objects_operation(freecad, False, "Doc", page_size=10)

    assert response.isError is False
    assert "Box" in response.content[0].text
    assert response.content[1].data == "png"
    assert response.structuredContent["data"]["objects"] == [{"Name": "Box"}]


def test_a_near_blank_screenshot_does_not_drop_get_object_properties():
    freecad = MagicMock()
    freecad.get_object.return_value = make_get_object_success(
        "Box",
        {"Name": "Box", "Expression": "QASrc#<<Dims>>.Height"},
    )
    freecad.get_active_screenshot.side_effect = _remote(_BLANK)

    response = get_object_operation(freecad, False, "QADst", "Box")

    assert response.isError is False, response.content[0].text
    assert "QASrc#<<Dims>>.Height" in response.content[0].text
    warning = response.structuredContent["data"]["screenshot_warning"]
    assert "near-blank" in warning


def test_an_empty_document_read_survives_a_screenshot_with_no_bounds():
    freecad = MagicMock()
    freecad.get_objects.return_value = _objects_page([])
    freecad.get_active_screenshot.side_effect = _remote(_BOUNDS)

    response = get_objects_operation(freecad, False, "QAActiveA", page_size=10)

    assert response.isError is False, response.content[0].text
    assert response.structuredContent["data"]["objects"] == []
    assert "renderable bounds" in response.structuredContent["data"]["screenshot_warning"]


def test_execute_code_keeps_its_output_when_the_screenshot_fails():
    freecad = MagicMock()
    freecad.execute_code.return_value = {"success": True, "message": "printed-ok"}
    freecad.get_active_screenshot.side_effect = _remote(_BLANK)

    response = execute_code_operation(
        freecad, False, "print('printed-ok')", capture_view=True, read_only=True
    )

    assert response.isError is False, response.content[0].text
    assert "printed-ok" in response.content[0].text
    assert "near-blank" in response.structuredContent["data"]["screenshot_warning"]
