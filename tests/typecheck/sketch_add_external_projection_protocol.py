"""Static contract examples for the sketch_add_external_projection collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sketch_add_external_projection_contract import (
    SketchAddExternalProjectionRequest,
    SketchAddExternalProjectionSuccess,
    SketchAddExternalProjectionDocument,
    SketchAddExternalProjectionName,
    SketchAddExternalProjectionReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sketch_add_external_projection import (
    SketchAddExternalProjectionCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sketch_add_external_projection import sketch_add_external_projection_operation


class CompleteSketchAddExternalProjectionDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: SketchAddExternalProjectionReadDocument) -> object:
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

    def validate_document_invariants(self, document: SketchAddExternalProjectionReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SketchAddExternalProjectionCollaborators = CompleteSketchAddExternalProjectionDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SketchAddExternalProjectionCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SketchAddExternalProjectionCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = SketchAddExternalProjectionRequest(doc_name=document_name, sketch_name="Value", source_ref="Value", projection_mode="Value", defining=False, allow_gui_geometry_loop=False)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(sketch_add_external_projection_operation(client, True, "Doc", "Value", "Value", "auto", False, True), CallToolResult)


def postcondition_surface_is_read_only(document: SketchAddExternalProjectionReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
