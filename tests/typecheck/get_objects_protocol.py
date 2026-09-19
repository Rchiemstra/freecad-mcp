"""Static contract examples for the get_objects collaborator boundary."""

from __future__ import annotations

from typing import assert_type

from addon.FreeCADMCP._shared.protocol.get_objects_contract import (
    DocumentName,
    GetObjectsRequest,
    GetObjectsSuccess,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_objects import (
    GetObjectsCollaborators,
    build_get_objects_request,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.core_ops.object_ops import get_objects_operation


class CompleteGetObjectsDouble:
    freecad: object

    def serialize_object(self, obj: object) -> dict[str, object]:
        return {"Name": "Box"}


def _request() -> GetObjectsRequest:
    request = build_get_objects_request("Doc")
    assert not isinstance(request, dict)
    return request


def _success_shape() -> GetObjectsSuccess:
    return {
        "contract_version": 1,
        "success": True,
        "ok": True,
        "outcome": "observed",
        "retry_safe": False,
        "doc_name": "Doc",
        "objects": [],
        "total_count": 0,
        "returned_count": 0,
        "page_size": 50,
        "complete": True,
        "next_cursor": None,
        "snapshot_id": "deadbeef",
    }


def test_static_contract_examples() -> None:
    collab: GetObjectsCollaborators = CompleteGetObjectsDouble()
    assert_type(collab, GetObjectsCollaborators)
    request = _request()
    assert_type(request.doc_name, DocumentName)
    assert_type(_success_shape(), GetObjectsSuccess)
    assert_type(get_objects_operation, object)
    assert_type(FreeCADConnection, type)
