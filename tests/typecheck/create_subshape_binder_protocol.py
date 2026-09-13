"""Static contract examples for the create_subshape_binder collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.create_subshape_binder_contract import (
    CreateSubshapeBinderRequest,
    CreateSubshapeBinderSuccess,
    CreateSubshapeBinderDocument,
    CreateSubshapeBinderName,
    CreateSubshapeBinderReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_subshape_binder import (
    CreateSubshapeBinderCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.create_subshape_binder import create_subshape_binder_operation


class CompleteCreateSubshapeBinderDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: CreateSubshapeBinderReadDocument) -> object:
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

    def validate_document_invariants(self, document: CreateSubshapeBinderReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CreateSubshapeBinderCollaborators = CompleteCreateSubshapeBinderDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CreateSubshapeBinderCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: CreateSubshapeBinderCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CreateSubshapeBinderRequest(doc_name=document_name, binder_name="Value", source_object="Value", sub_elements=None, target_body=None, target_container=None, relative=False, sync_placement=True, if_exists="error")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(create_subshape_binder_operation(client, True, "Doc", "Value", "Value", None, None, None, False, True, "error"), CallToolResult)


def postcondition_surface_is_read_only(document: CreateSubshapeBinderReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
