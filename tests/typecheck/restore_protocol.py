"""Static contract examples for the restore collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.restore_contract import (
    RestoreRequest,
    RestoreSuccess,
    RestoreDocument,
    RestoreName,
    RestoreReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.restore import (
    RestoreCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.restore import restore_operation


class CompleteRestoreDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: RestoreReadDocument) -> object:
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

    def validate_document_invariants(self, document: RestoreReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: RestoreCollaborators = CompleteRestoreDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> RestoreCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: RestoreCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = RestoreRequest(doc_name=document_name, snapshot_id=None)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(restore_operation(client, True, "Doc", None), CallToolResult)


def postcondition_surface_is_read_only(document: RestoreReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
