"""Static contract examples for the sketch_edit_constraint collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_edit_constraint_contract import (
    DocumentName,
    SketchEditConstraintRequest,
    SketchEditConstraintSuccess,
    SketchEditConstraintReadDocument,
    SketchName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_edit_constraint import (
    SketchEditConstraintCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.sketch_edit_constraint_contract import (
    SketchName as ClientSketchName,
)
from freecad_mcp._shared.protocol.sketch_edit_constraint_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_edit_constraint import sketch_edit_constraint_operation


class CompleteSketchEditConstraintDouble:
    """A test double that satisfies every sketch_edit_constraint dependency."""

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

    def validate_document_invariants(self, document: SketchEditConstraintReadDocument) -> object:
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

    def validate_document_invariants(self, document: SketchEditConstraintReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: SketchEditConstraintCollaborators = CompleteSketchEditConstraintDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchEditConstraintCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SketchEditConstraintCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
sketch_name = SketchName("MainSketch")
valid_request = SketchEditConstraintRequest(doc_name=document_name, sketch_name=sketch_name, value=7.0, name="R")
swapped_request = SketchEditConstraintRequest(
    doc_name=sketch_name,  # type: ignore[arg-type]
    sketch_name=document_name,  # type: ignore[arg-type]
    value=7.0,
    name="R",
)

incomplete_success: SketchEditConstraintSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientSketchName("MainSketch")
    assert_type(client.sketch_edit_constraint(document, named, 7.0, "R", None), object)
    assert_type(sketch_edit_constraint_operation(client, True, "Doc", "Sketch", 7.0, "R", None), CallToolResult)
    client.sketch_edit_constraint(named, document, 7.0, "R", None)  # type: ignore[arg-type]
    client.sketch_edit_constraint("Doc", "Sketch", 7.0, "R", None)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: SketchEditConstraintReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
