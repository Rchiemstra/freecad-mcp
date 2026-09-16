"""Static contract examples for the sketch_add_geometry collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_add_geometry_contract import (
    DocumentName,
    SketchAddGeometryRequest,
    SketchAddGeometrySuccess,
    SketchAddGeometryReadDocument,
    SketchName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_geometry import (
    SketchAddGeometryCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_add_geometry_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_add_geometry_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_add_geometry import sketch_add_geometry_operation


class CompleteSketchAddGeometryDouble:
    """A test double that satisfies every sketch_add_geometry dependency."""

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

    def validate_document_invariants(self, document: SketchAddGeometryReadDocument) -> object:
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

    def validate_document_invariants(self, document: SketchAddGeometryReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: SketchAddGeometryCollaborators = CompleteSketchAddGeometryDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAddGeometryCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SketchAddGeometryCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("MainSketch")
valid_request = SketchAddGeometryRequest(doc_name=document_name, sketch_name=sketch_name, geometry=({"type": "circle"},))
swapped_request = SketchAddGeometryRequest(
    doc_name=sketch_name,  # type: ignore[arg-type]
    sketch_name=document_name,  # type: ignore[arg-type]
    geometry=({"type": "circle"},),
)

incomplete_success: SketchAddGeometrySuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientSketchName("MainSketch")
    assert_type(client.sketch_add_geometry(document, named, [{"type": "circle"}]), object)
    assert_type(sketch_add_geometry_operation(client, True, "Doc", "Sketch", [{"type": "circle", "radius": 5}]), CallToolResult)
    client.sketch_add_geometry(named, document, [{"type": "circle"}])  # type: ignore[arg-type]
    client.sketch_add_geometry("Doc", "Sketch", [{"type": "circle"}])  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchAddGeometryReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
