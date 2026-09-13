"""Static contract examples for the build_path_wire collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.build_path_wire_contract import (
    BuildPathWireRequest,
    BuildPathWireSuccess,
    BuildPathWireDocument,
    BuildPathWireName,
    BuildPathWireReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.build_path_wire import (
    BuildPathWireCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.build_path_wire import build_path_wire_operation


class CompleteBuildPathWireDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: BuildPathWireReadDocument) -> object:
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

    def validate_document_invariants(self, document: BuildPathWireReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: BuildPathWireCollaborators = CompleteBuildPathWireDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> BuildPathWireCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: BuildPathWireCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = BuildPathWireRequest(doc_name=document_name, wire_name="Value", segments=[{"sketch": "Seed", "geo_index": 0}], tolerance_mm=0.5, container=None, if_exists="error")


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(build_path_wire_operation(client, True, "Doc", "Value", [{"sketch": "Seed", "geo_index": 0}], 0.5, None, "error"), CallToolResult)


def postcondition_surface_is_read_only(document: BuildPathWireReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
