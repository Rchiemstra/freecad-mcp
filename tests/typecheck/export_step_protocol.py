"""Static contract examples for the export_step collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.export_step_contract import (
    ExportStepRequest,
    ExportStepSuccess,
    MutationReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_step import (
    ExportStepCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.export_step_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.export_step import export_step_operation


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


complete: ExportStepCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> ExportStepCollaborators:
    return collaborators


missing_postcondition: ExportStepCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = ExportStepRequest
incomplete_success: ExportStepSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    assert_type(client.export_step(document, "/tmp/out.step"), object)
    assert_type(export_step_operation(client, "Doc", "/tmp/out.step"), CallToolResult)
    client.export_step("/tmp/out.step", "Doc")  # type: ignore[arg-type]
    client.export_step("Doc", "/tmp/out.step")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
