"""Static contract examples for the sketch_add_constraint collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_add_constraint_contract import (
    DocumentName,
    SketchAddConstraintRequest,
    SketchAddConstraintSuccess,
    SketchAddConstraintReadDocument,
    SketchName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_constraint import (
    SketchAddConstraintCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_add_constraint_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_add_constraint_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_add_constraint import sketch_add_constraint_operation


class CompleteSketchAddConstraintDouble:
    """A test double that satisfies every sketch_add_constraint dependency."""

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

    def validate_document_invariants(self, document: SketchAddConstraintReadDocument) -> object:
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

    def validate_document_invariants(self, document: SketchAddConstraintReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: SketchAddConstraintCollaborators = CompleteSketchAddConstraintDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAddConstraintCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SketchAddConstraintCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("MainSketch")
valid_request = SketchAddConstraintRequest(doc_name=document_name, sketch_name=sketch_name, constraints=({"type": "Radius", "geo": 0, "value": 5},))
swapped_request = SketchAddConstraintRequest(
    doc_name=sketch_name,  # type: ignore[arg-type]
    sketch_name=document_name,  # type: ignore[arg-type]
    constraints=({"type": "Radius", "geo": 0, "value": 5},),
)

incomplete_success: SketchAddConstraintSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientSketchName("MainSketch")
    assert_type(client.sketch_add_constraint(document, named, [{"type": "Radius", "geo": 0, "value": 5}]), object)
    assert_type(sketch_add_constraint_operation(client, True, "Doc", "Sketch", [{"type": "Radius", "geo": 0, "value": 5}]), CallToolResult)
    client.sketch_add_constraint(named, document, [{"type": "Radius", "geo": 0, "value": 5}])  # type: ignore[arg-type]
    client.sketch_add_constraint("Doc", "Sketch", [{"type": "Radius", "geo": 0, "value": 5}])  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchAddConstraintReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
