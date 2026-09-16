"""Static contract examples for the sweep_pipe collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.sweep_pipe_contract import (
    SweepPipeRequest,
    SweepPipeSuccess,
    SweepPipeDocument,
    SweepPipeName,
    SweepPipeReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.sweep_pipe import (
    SweepPipeCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.sweep_pipe import sweep_pipe_operation


class CompleteSweepPipeDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: SweepPipeReadDocument) -> object:
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

    def validate_document_invariants(self, document: SweepPipeReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: SweepPipeCollaborators = CompleteSweepPipeDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> SweepPipeCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: SweepPipeCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = SweepPipeRequest(doc_name=document_name, path_wire="Value", diameter_mm=1.0, solid_name="Value", profile_mode="Value", color=None, container=None, if_exists="error")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(sweep_pipe_operation(client, True, "Doc", "Value", 1.0, "Value", "Value", None, None, "error"), CallToolResult)


def postcondition_surface_is_read_only(document: SweepPipeReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
