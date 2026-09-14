"""Static contract examples for the sketch_toggle_construction collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_toggle_construction_contract import (
    SketchToggleConstructionRequest,
    SketchToggleConstructionSuccess,
    SketchDocument,
    SketchFreeCAD,
    SketchName,
    SketchPart,
    SketchReadDocument,
    SketchSketcher,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_toggle_construction import (
    SketchToggleConstructionCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_toggle_construction_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_toggle_construction_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_toggle_construction import sketch_toggle_construction_operation


class CompleteSketchToggleConstructionDouble:
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


complete: SketchToggleConstructionCollaborators = CompleteSketchToggleConstructionDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchToggleConstructionCollaborators:
    return collaborators


missing_postcondition: SketchToggleConstructionCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("Sketch")
valid_request = SketchToggleConstructionRequest(
    doc_name=document_name,
    sketch_name=sketch_name,
    geo_indices=(0,),
    construction=False,
)
incomplete_success: SketchToggleConstructionSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    sketch = ClientSketchName("Sketch")
    assert_type(client.sketch_toggle_construction(document, sketch, [0], False), object)
    assert_type(sketch_toggle_construction_operation(client, True, "Doc", "Sketch", [0], False), CallToolResult)
    client.sketch_toggle_construction(sketch, document, [0], False)  # type: ignore[arg-type]
    client.sketch_toggle_construction("Doc", "Sketch", [0], False)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]


__all__: list[str] = []
