"""Static contract examples for the sketch_add_arc_of_ellipse collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_add_arc_of_ellipse_contract import (
    SketchAddArcOfEllipseRequest,
    SketchAddArcOfEllipseSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_arc_of_ellipse import (
    SketchAddArcOfEllipseCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_add_arc_of_ellipse_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_add_arc_of_ellipse_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_add_arc_of_ellipse import sketch_add_arc_of_ellipse_operation


class CompleteSketchAddArcOfEllipseDouble:
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


complete: SketchAddArcOfEllipseCollaborators = CompleteSketchAddArcOfEllipseDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAddArcOfEllipseCollaborators:
    return collaborators


missing_postcondition: SketchAddArcOfEllipseCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchAddArcOfEllipseRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    cx=0.0,
    cy=0.0,
    major_radius=0.0,
    minor_radius=0.0,
    start_angle=0.0,
    end_angle=0.0,
    angle=0.0,
    construction=False,
)
incomplete_success: SketchAddArcOfEllipseSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_add_arc_of_ellipse(document, sketch, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False), object)
    assert_type(sketch_add_arc_of_ellipse_operation(client, True, "Doc", "Sketch", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False), CallToolResult)
    client.sketch_add_arc_of_ellipse(sketch, document, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)  # type: ignore[arg-type]
    client.sketch_add_arc_of_ellipse("Doc", "Sketch", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
