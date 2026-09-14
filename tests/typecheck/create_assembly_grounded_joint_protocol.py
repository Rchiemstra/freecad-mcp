"""Static contract examples for the create_assembly_grounded_joint collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_assembly_grounded_joint_contract import (
    CreateAssemblyGroundedJointRequest,
    CreateAssemblyGroundedJointSuccess,
    MutationReadDocument,
    DocumentName,
    AssemblyName,
    ComponentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_assembly_grounded_joint import (
    CreateAssemblyGroundedJointCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.create_assembly_grounded_joint_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.create_assembly_grounded_joint_contract import AssemblyName as ClientSecond
from freecad_mcp._shared.protocol.create_assembly_grounded_joint_contract import (
    ComponentName as ClientComponentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_assembly_grounded_joint import create_assembly_grounded_joint_operation


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


complete: CreateAssemblyGroundedJointCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreateAssemblyGroundedJointCollaborators:
    return collaborators


missing_postcondition: CreateAssemblyGroundedJointCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = (CreateAssemblyGroundedJointRequest, DocumentName, AssemblyName, ComponentName)
incomplete_success: CreateAssemblyGroundedJointSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Assembly")
    assert_type(client.create_assembly_grounded_joint(document, name, ClientComponentName("Base")), object)
    assert_type(create_assembly_grounded_joint_operation(client, True, "Doc", "Assembly", "Base"), CallToolResult)
    client.create_assembly_grounded_joint(name, document, ClientComponentName("Base"))  # type: ignore[arg-type]
    client.create_assembly_grounded_joint("Doc", "Assembly", "Base")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
