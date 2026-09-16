from unittest.mock import MagicMock

import pytest

from freecad_mcp._shared.protocol.create_object_contract import (
    ObjectName as CreateObjectName,
    make_create_object_success,
)
from freecad_mcp._shared.protocol.edit_object_contract import (
    ObjectName as EditObjectName,
    make_edit_object_success,
)
from freecad_mcp.operations.core_ops.object_ops import (
    create_object_operation,
    edit_object_operation,
)


@pytest.mark.parametrize(
    ("operation", "method_name", "args", "payload"),
    (
        (
            create_object_operation,
            "create_object",
            (False, "Doc", "Part::Box", "Box"),
            make_create_object_success(CreateObjectName("Box"), "Part::Box", "Box"),
        ),
        (
            edit_object_operation,
            "edit_object",
            (False, "Doc", "Box", {"Length": 10}),
            make_edit_object_success(EditObjectName("Box"), "Box"),
        ),
    ),
)
def test_committed_object_mutation_survives_screenshot_failure(
    operation, method_name, args, payload
):
    connection = MagicMock()
    getattr(connection, method_name).return_value = payload
    connection.get_active_screenshot.side_effect = RuntimeError("viewer unavailable")

    response = operation(connection, *args)

    assert not response.isError
    assert response.structuredContent["data"]["presentation_warning"] == (
        "Screenshot capture failed: viewer unavailable"
    )
    getattr(connection, method_name).assert_called_once()
