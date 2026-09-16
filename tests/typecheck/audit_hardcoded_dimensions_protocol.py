"""Static contract examples for the audit_hardcoded_dimensions collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.audit_hardcoded_dimensions_contract import (
    AuditHardcodedDimensionsRequest,
    AuditHardcodedDimensionsSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.audit_hardcoded_dimensions import (
    AuditHardcodedDimensionsCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.audit_hardcoded_dimensions_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.audit_hardcoded_dimensions_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.audit_hardcoded_dimensions import audit_hardcoded_dimensions_operation


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


complete: AuditHardcodedDimensionsCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> AuditHardcodedDimensionsCollaborators:
    return collaborators


missing_postcondition: AuditHardcodedDimensionsCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = AuditHardcodedDimensionsRequest
incomplete_success: AuditHardcodedDimensionsSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.audit_hardcoded_dimensions(document, name, True), object)
    assert_type(audit_hardcoded_dimensions_operation(client, "Doc", "Box", True), CallToolResult)
    client.audit_hardcoded_dimensions(0, "Box", True)  # type: ignore[arg-type]
    client.audit_hardcoded_dimensions("Doc", 0, True)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
