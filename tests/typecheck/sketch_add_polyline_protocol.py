"""Static contract examples for the sketch_add_polyline collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_add_polyline_contract import (
    SketchAddPolylineRequest,
    SketchAddPolylineSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_polyline import (
    SketchAddPolylineCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_add_polyline_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_add_polyline_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_add_polyline import sketch_add_polyline_operation


class CompleteSketchAddPolylineDouble:
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


complete: SketchAddPolylineCollaborators = CompleteSketchAddPolylineDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAddPolylineCollaborators:
    return collaborators


missing_postcondition: SketchAddPolylineCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchAddPolylineRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    points=((0.0, 0.0), (1.0, 0.0)),
    closed=False,
    construction=False,
)
incomplete_success: SketchAddPolylineSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_add_polyline(document, sketch, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False, False), object)
    assert_type(sketch_add_polyline_operation(client, True, "Doc", "Sketch", [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False, False), CallToolResult)
    client.sketch_add_polyline(sketch, document, [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False, False)  # type: ignore[arg-type]
    client.sketch_add_polyline("Doc", "Sketch", [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}], False, False)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
