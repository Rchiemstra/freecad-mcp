from unittest.mock import MagicMock

import pytest

from freecad_mcp.operations.core_ops.object_ops import (
    create_object_operation,
    edit_object_operation,
)
from freecad_mcp.operations.core_ops.run_code import _run_code


@pytest.mark.parametrize(
    ("operation", "method_name", "args"),
    (
        (
            create_object_operation,
            "create_object",
            (False, "Doc", "Part::Box", "Box"),
        ),
        (
            edit_object_operation,
            "edit_object",
            (False, "Doc", "Box", {"Length": 10}),
        ),
    ),
)
def test_committed_object_mutation_survives_screenshot_failure(operation, method_name, args):
    connection = MagicMock()
    getattr(connection, method_name).return_value = {
        "success": True,
        "ok": True,
        "object_name": "Box",
    }
    connection.get_active_screenshot.side_effect = RuntimeError("viewer unavailable")

    response = operation(connection, *args)

    assert not response.isError
    assert response.structuredContent["data"]["presentation_warning"] == (
        "Screenshot capture failed: viewer unavailable"
    )
    getattr(connection, method_name).assert_called_once()


def test_committed_generated_code_survives_screenshot_failure():
    connection = MagicMock()
    connection.execute_code.return_value = {"success": True, "message": "committed"}
    connection.get_active_screenshot.side_effect = RuntimeError("viewer unavailable")

    response = _run_code(
        connection, False, "pass", "Rectangle created", "Failed to create rectangle"
    )

    assert not response.isError
    assert response.structuredContent["data"]["presentation_warning"] == (
        "Screenshot capture failed: viewer unavailable"
    )
