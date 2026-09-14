"""Static contract examples for the run_fem_analysis collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.run_fem_analysis_contract import (
    RunFemAnalysisRequest,
    RunFemAnalysisSuccess,
    RunFemAnalysisDocument,
    RunFemAnalysisName,
    RunFemAnalysisReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.run_fem_analysis import (
    RunFemAnalysisCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.run_fem_analysis import run_fem_analysis_operation


class CompleteRunFemAnalysisDouble:
    """A test double that satisfies every dependency."""

    def validate_document_invariants(self, document: RunFemAnalysisReadDocument) -> object:
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

    def validate_document_invariants(self, document: RunFemAnalysisReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: RunFemAnalysisCollaborators = CompleteRunFemAnalysisDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> RunFemAnalysisCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: RunFemAnalysisCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
valid_request = RunFemAnalysisRequest(doc_name=document_name, analysis_name="Value", timeout=600)


def public_client_preserves_names(client: FreeCADConnection) -> None:
    assert_type(run_fem_analysis_operation(client, True, "Doc", "Value", 600), CallToolResult)


def postcondition_surface_is_read_only(document: RunFemAnalysisReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("Body")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
