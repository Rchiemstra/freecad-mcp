"""Static contract examples for the sketch_import_points collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_import_points_contract import (
    SketchImportPointsRequest,
    SketchImportPointsSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_import_points import (
    SketchImportPointsCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_import_points_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_import_points_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_import_points import sketch_import_points_operation


class CompleteSketchImportPointsDouble:
    freecad: SketchFreeCAD
    part: SketchPart
    sketcher: SketchSketcher

    def validate_document_invariants(self, document: SketchReadDocument) -> object:
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
    freecad: SketchFreeCAD
    part: SketchPart
    sketcher: SketchSketcher

    def validate_document_invariants(self, document: SketchReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SketchImportPointsCollaborators = CompleteSketchImportPointsDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchImportPointsCollaborators:
    return collaborators


missing_postcondition: SketchImportPointsCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchImportPointsRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    points=((0.0, 0.0), (1.0, 0.0)),
    construction=False,
)
incomplete_success: SketchImportPointsSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_import_points(document, sketch, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False), object)
    assert_type(sketch_import_points_operation(client, True, "Doc", "Sketch", [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False), CallToolResult)
    client.sketch_import_points(sketch, document, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False)  # type: ignore[arg-type]
    client.sketch_import_points("Doc", "Sketch", [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
