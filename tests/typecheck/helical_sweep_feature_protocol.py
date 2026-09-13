"""Static contract examples for the helical_sweep_feature collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.helical_sweep_feature_contract import (
    HelicalSweepFeatureSuccess,
    FeatureDocument,
    FeatureName,
    FeatureReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.helical_sweep_feature import (
    HelicalSweepFeatureCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.helical_sweep_feature_contract import (
    FeatureName as ClientFeatureName,
)
from freecad_mcp._shared.protocol.helical_sweep_feature_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.helical_sweep_feature import helical_sweep_feature_operation


class CompleteHelicalSweepFeatureDouble:
    """A test double that satisfies every helical_sweep_feature dependency."""

    def validate_document_invariants(self, document: FeatureReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[FeatureDocument], object],
        postcondition: Callable[[FeatureReadDocument], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


class MissingPostconditionDouble:
    """A stale double that cannot receive the native phase contract."""

    def validate_document_invariants(self, document: FeatureReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[FeatureDocument], object],
        *,
        structural: bool = True,
    ) -> object:
        return None


complete: HelicalSweepFeatureCollaborators = CompleteHelicalSweepFeatureDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> HelicalSweepFeatureCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators  # type: ignore[return-value]


missing_postcondition: HelicalSweepFeatureCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
feature_name = FeatureName("Feature")
incomplete_success: HelicalSweepFeatureSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    feature = ClientFeatureName("Feature")
    assert_type(client.helical_sweep_feature(document, feature, feature, 1.0, 1.0, 1.0), object)
    assert_type(helical_sweep_feature_operation(client, True, document, feature, feature, 1.0, 1.0, 1.0), CallToolResult)
    client.helical_sweep_feature(feature, document, document, 1.0, 1.0, 1.0)  # type: ignore[arg-type]
    client.helical_sweep_feature("Doc", "Feature", "Feature", 1.0, 1.0, 1.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: FeatureReadDocument) -> None:
    document.addObject("PartDesign::Body", "Body")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    inspected = document.getObject("Body")
    if inspected is not None:
        inspected.Label = "Changed"  # type: ignore[misc]


__all__: list[str] = []
