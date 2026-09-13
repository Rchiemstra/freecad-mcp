"""Static contract examples for the capture_state collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.capture_state_contract import (
    CaptureStateRequest,
    CaptureStateSuccess,
    CaptureStateDocument,
    CaptureStateName,
    CaptureStateReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.capture_state import (
    CaptureStateCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.capture_state import capture_state_operation


class CompleteCaptureStateDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: CaptureStateReadDocument) -> object:
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

    def validate_document_invariants(self, document: CaptureStateReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: CaptureStateCollaborators = CompleteCaptureStateDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> CaptureStateCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: CaptureStateCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = CaptureStateRequest(doc_name=document_name, object_names=None)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(capture_state_operation(client, True, "Doc", None), CallToolResult)


def postcondition_surface_is_read_only(document: CaptureStateReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
