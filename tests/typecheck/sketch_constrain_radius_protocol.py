"""Static contract examples for the sketch_constrain_radius collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_constrain_radius_contract import (
    SketchConstrainRadiusRequest,
    SketchConstrainRadiusSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_constrain_radius import (
    SketchConstrainRadiusCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_constrain_radius_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_constrain_radius_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_constrain_radius import sketch_constrain_radius_operation


class CompleteSketchConstrainRadiusDouble:
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


complete: SketchConstrainRadiusCollaborators = CompleteSketchConstrainRadiusDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchConstrainRadiusCollaborators:
    return collaborators


missing_postcondition: SketchConstrainRadiusCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchConstrainRadiusRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    geo=0,
    value=0.0,
    name="x",
)
incomplete_success: SketchConstrainRadiusSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_constrain_radius(document, sketch, 0, 0.0, "x"), object)
    assert_type(sketch_constrain_radius_operation(client, True, "Doc", "Sketch", 0, 0.0, "x"), CallToolResult)
    client.sketch_constrain_radius(sketch, document, 0, 0.0, "x")  # type: ignore[arg-type]
    client.sketch_constrain_radius("Doc", "Sketch", 0, 0.0, "x")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
