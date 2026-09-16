"""Static contract examples for the get_sketch_geometry collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.get_sketch_geometry_contract import (
    GetSketchGeometryRequest,
    GetSketchGeometrySuccess,
    MutationReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.get_sketch_geometry import (
    GetSketchGeometryCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.get_sketch_geometry_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.get_sketch_geometry_contract import SketchName as ClientSketchName
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.get_sketch_geometry import get_sketch_geometry_operation


class CompleteDouble:
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


class MissingPostconditionDouble:
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: GetSketchGeometryCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> GetSketchGeometryCollaborators:
    return collaborators


missing_postcondition: GetSketchGeometryCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = GetSketchGeometryRequest
incomplete_success: GetSketchGeometrySuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.get_sketch_geometry(document, sketch), object)
    assert_type(get_sketch_geometry_operation(client, "Doc", "Sketch"), CallToolResult)
    client.get_sketch_geometry(0, "Sketch")  # type: ignore[arg-type]
    client.get_sketch_geometry("Doc", 0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
