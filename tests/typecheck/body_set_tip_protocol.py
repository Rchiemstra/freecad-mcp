"""Static contract examples for the body-set-tip collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.body_set_tip_contract import (
    BodyName,
    BodySetTipRequest,
    BodySetTipSuccess,
    DocumentName,
    FeatureName,
    TipBodyDocument,
    TipReadDocument,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_set_tip import (
    BodySetTipCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.body_set_tip_contract import (
    BodyName as ClientBodyName,
)
from freecad_mcp._shared.protocol.body_set_tip_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp._shared.protocol.body_set_tip_contract import (
    FeatureName as ClientFeatureName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.body_ops import body_set_tip_operation
from freecad_mcp.operations.parametric_ops.body_set_tip import (
    body_set_tip_operation as typed_body_set_tip_operation,
)


class CompleteBodySetTipDouble:
    """A test double that satisfies every body-set-tip dependency."""

    def validate_document_invariants(self, document: TipReadDocument) -> object:
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

    def validate_document_invariants(self, document: TipReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: BodySetTipCollaborators = CompleteBodySetTipDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> BodySetTipCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


# With --warn-unused-ignores, mypy fails if the protocol becomes loose enough
# to accept a double that cannot receive the native postcondition contract.
missing_postcondition: BodySetTipCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
body_name = BodyName("MainBody")
feature_name = FeatureName("Pocket")
valid_request = BodySetTipRequest(
    doc_name=document_name,
    body_name=body_name,
    feature_name=feature_name,
)
swapped_request = BodySetTipRequest(
    doc_name=body_name,  # type: ignore[arg-type]
    body_name=feature_name,  # type: ignore[arg-type]
    feature_name=document_name,  # type: ignore[arg-type]
)

# A committed response cannot be constructed without its assigned names or
# the remaining required state fields.
incomplete_success: BodySetTipSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    body = ClientBodyName("Body")
    feature = ClientFeatureName("Pad")
    assert_type(client.body_set_tip(document, body, feature), object)
    assert_type(body_set_tip_operation(client, True, "Doc", "Body", "Pad"), CallToolResult)
    assert_type(
        typed_body_set_tip_operation(client, True, "Doc", "Body", "Pad"), CallToolResult
    )
    client.body_set_tip(body, feature, document)  # type: ignore[arg-type]
    client.body_set_tip("Doc", "Body", "Pad")  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: TipReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    body = document.getObject("Body")
    if body is not None:
        body.Label = "Changed"  # type: ignore[misc]
        body.Tip = body  # type: ignore[misc]


def apply_surface_can_write_tip(document: TipBodyDocument) -> None:
    body = document.getObject("Body")
    feature = document.getObject("Pocket")
    if body is not None and feature is not None:
        body.Tip = feature


__all__: list[str] = []
