"""Static contract examples for the preview_attachment collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.preview_attachment_contract import (
    PreviewAttachmentRequest,
    PreviewAttachmentSuccess,
    PreviewAttachmentDocument,
    PreviewAttachmentName,
    PreviewAttachmentReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.preview_attachment import (
    PreviewAttachmentCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.preview_attachment import preview_attachment_operation


class CompletePreviewAttachmentDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: PreviewAttachmentReadDocument) -> object:
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

    def validate_document_invariants(self, document: PreviewAttachmentReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: PreviewAttachmentCollaborators = CompletePreviewAttachmentDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> PreviewAttachmentCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: PreviewAttachmentCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = PreviewAttachmentRequest(doc_name=document_name, datum_name="Value")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(preview_attachment_operation(client, True, "Doc", "Value"), CallToolResult)


def postcondition_surface_is_read_only(document: PreviewAttachmentReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
