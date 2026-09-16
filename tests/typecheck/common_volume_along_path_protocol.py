"""Static contract examples for the common_volume_along_path collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.common_volume_along_path_contract import (
    CommonVolumeAlongPathRequest,
    CommonVolumeAlongPathSuccess,
    MutationReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.common_volume_along_path import (
    CommonVolumeAlongPathCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.common_volume_along_path_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.common_volume_along_path import common_volume_along_path_operation


class CompleteDouble:
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
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
    def validate_document_invariants(self, document: MutationReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CommonVolumeAlongPathCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CommonVolumeAlongPathCollaborators:
    return collaborators


missing_postcondition: CommonVolumeAlongPathCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = CommonVolumeAlongPathRequest
incomplete_success: CommonVolumeAlongPathSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.common_volume_along_path(document, "Mover", ["Wall"], None, 2, [{"x": 0, "y": 0, "z": 0}]), object)
    assert_type(common_volume_along_path_operation(client, "Doc", "Mover", ["Wall"], samples=[{"x": 0, "y": 0, "z": 0}]), CallToolResult)
    client.common_volume_along_path("Mover", "Doc", ["Wall"])  # type: ignore[arg-type]
    client.common_volume_along_path("Doc", "Mover", ["Wall"])  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
