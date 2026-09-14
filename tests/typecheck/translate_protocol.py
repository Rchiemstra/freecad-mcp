"""Static contract examples for the translate collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.translate_contract import (
    TranslateRequest,
    TranslateSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.translate import (
    TranslateCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.translate_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.translate_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.translate import translate_operation


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


complete: TranslateCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> TranslateCollaborators:
    return collaborators


missing_postcondition: TranslateCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = TranslateRequest
incomplete_success: TranslateSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.translate(document, name, 1.0, 0.0, 0.0), object)
    assert_type(translate_operation(client, True, "Doc", "Box", 1.0, 0.0, 0.0), CallToolResult)
    client.translate(name, document, 1.0, 0.0, 0.0)  # type: ignore[arg-type]
    client.translate("Doc", "Box", 1.0, 0.0, 0.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
