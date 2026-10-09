"""Committed screenshots must show the document that was changed.

With documents A and B open and A active, create_object in B returned a
picture of A: the capture always used the GUI's active document.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.delete_object_contract import make_delete_object_success
from freecad_mcp.operations.parametric_ops.delete_object import delete_object_operation
from freecad_mcp.responses.tool_results import capture_committed_screenshot

pytestmark = pytest.mark.unit


def test_the_capture_asks_for_the_changed_document():
    freecad = MagicMock()
    freecad.get_active_screenshot.return_value = "png"

    image = capture_committed_screenshot(
        freecad, {}, only_text_feedback=False, document="B"
    )

    assert image == "png"
    freecad.get_active_screenshot.assert_called_once_with(document="B")


def test_an_operation_passes_its_document_to_the_capture():
    freecad = MagicMock()
    freecad.delete_object.return_value = make_delete_object_success("Box", ["Box"])
    freecad.get_active_screenshot.return_value = "png"

    delete_object_operation(freecad, False, "B", "Box")

    freecad.get_active_screenshot.assert_called_once_with(document="B")
