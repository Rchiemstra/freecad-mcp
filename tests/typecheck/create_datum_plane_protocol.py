"""Static contract examples for the create_datum_plane collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_datum_plane_contract import (
    CreateDatumPlaneRequest,
    CreateDatumPlaneSuccess,
    CreateDatumPlaneDocument,
    CreateDatumPlaneName,
    CreateDatumPlaneReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_datum_plane import (
    CreateDatumPlaneCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_datum_plane import create_datum_plane_operation


class CompleteCreateDatumPlaneDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: CreateDatumPlaneReadDocument) -> object:
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

    def validate_document_invariants(self, document: CreateDatumPlaneReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CreateDatumPlaneCollaborators = CompleteCreateDatumPlaneDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreateDatumPlaneCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: CreateDatumPlaneCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CreateDatumPlaneRequest(doc_name=document_name, plane_name="Value", body_name="Value", mode="Value", source_ref=None, face_a=None, face_b=None, offset_along_normal=None, map_mode="Value", if_exists="error")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(create_datum_plane_operation(client, True, "Doc", "Value", "Value", "Value", None, None, None, None, "Value", "error"), CallToolResult)


def postcondition_surface_is_read_only(document: CreateDatumPlaneReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
