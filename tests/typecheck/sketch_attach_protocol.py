"""Static contract examples for the sketch_attach collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_attach_contract import (
    DocumentName,
    SketchAttachRequest,
    SketchAttachSuccess,
    SketchAttachReadDocument,
    SketchName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_attach import (
    SketchAttachCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_attach_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_attach_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_attach import sketch_attach_operation


class CompleteSketchAttachDouble:
    """A test double that satisfies every sketch_attach dependency."""

    freecad = object()
    part = object()
    sketcher = object()

    def dict_to_placement(self, value: object) -> object:
        return value

    def placement_to_dict(self, value: object) -> object:
        return value

    def set_extrusion_symmetric(self, feature: object, value: bool) -> object:
        return None

    def set_feature_bool(
        self, feature: object, property_names: tuple[str, ...], value: bool
    ) -> object:
        return None

    def validate_document_invariants(self, document: SketchAttachReadDocument) -> object:
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
    """A stale double that cannot receive the native phase contract."""

    freecad = object()
    part = object()
    sketcher = object()

    def dict_to_placement(self, value: object) -> object:
        return value

    def placement_to_dict(self, value: object) -> object:
        return value

    def set_extrusion_symmetric(self, feature: object, value: bool) -> object:
        return None

    def set_feature_bool(
        self, feature: object, property_names: tuple[str, ...], value: bool
    ) -> object:
        return None

    def validate_document_invariants(self, document: SketchAttachReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: SketchAttachCollaborators = CompleteSketchAttachDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAttachCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SketchAttachCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("MainSketch")
valid_request = SketchAttachRequest(doc_name=document_name, sketch_name=sketch_name, support="XY_Plane")
swapped_request = SketchAttachRequest(
    doc_name=sketch_name,  # type: ignore[arg-type]
    sketch_name=document_name,  # type: ignore[arg-type]
    support="XY_Plane",
)

incomplete_success: SketchAttachSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientSketchName("MainSketch")
    assert_type(client.sketch_attach(document, named, "XY_Plane"), object)
    assert_type(sketch_attach_operation(client, True, "Doc", "Sketch", "XY_Plane"), CallToolResult)
    client.sketch_attach(named, document, "XY_Plane")  # type: ignore[arg-type]
    client.sketch_attach("Doc", "Sketch", "XY_Plane")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchAttachReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
