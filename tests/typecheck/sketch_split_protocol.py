"""Static contract examples for the sketch_split collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_split_contract import (
    SketchSplitRequest,
    SketchSplitSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_split import (
    SketchSplitCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_split_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_split_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_split import sketch_split_operation


class CompleteSketchSplitDouble:
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


complete: SketchSplitCollaborators = CompleteSketchSplitDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchSplitCollaborators:
    return collaborators


missing_postcondition: SketchSplitCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchSplitRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    geo_index=0,
    point_x=0.0,
    point_y=0.0,
)
incomplete_success: SketchSplitSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_split(document, sketch, 0, 0.0, 0.0), object)
    assert_type(sketch_split_operation(client, True, "Doc", "Sketch", 0, 0.0, 0.0), CallToolResult)
    client.sketch_split(sketch, document, 0, 0.0, 0.0)  # type: ignore[arg-type]
    client.sketch_split("Doc", "Sketch", 0, 0.0, 0.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
