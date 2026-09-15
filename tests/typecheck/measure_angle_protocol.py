"""Static contract examples for the measure_angle collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.measure_angle_contract import (
    MeasureAngleRequest,
    MeasureAngleSuccess,
    MutationReadDocument,
    DocumentName,
    ObjectName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.measure_angle import (
    MeasureAngleCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.measure_angle_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.measure_angle_contract import ObjectName as ClientSecond
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.measure_angle import measure_angle_operation


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


complete: MeasureAngleCollaborators = CompleteDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> MeasureAngleCollaborators:
    return collaborators


missing_postcondition: MeasureAngleCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]


_ = MeasureAngleRequest
incomplete_success: MeasureAngleSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    name = ClientSecond("Box")
    assert_type(client.measure_angle(document, "Box:Edge1", "Box:Edge2"), object)
    assert_type(measure_angle_operation(client, "Doc", "Box:Edge1", "Box:Edge2"), CallToolResult)
    client.measure_angle(0, "Box:Edge1", "Box:Edge2")  # type: ignore[arg-type]
    client.measure_angle("Doc", 0, "Box:Edge2")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: MutationReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
