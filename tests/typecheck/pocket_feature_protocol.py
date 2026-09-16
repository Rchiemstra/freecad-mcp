"""Static contract examples for the pocket_feature collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.pocket_feature_contract import (
    DocumentName,
    PocketFeatureRequest,
    PocketFeatureSuccess,
    PocketFeatureReadDocument,
    PocketName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pocket_feature import (
    PocketFeatureCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.pocket_feature_contract import (
    PocketName as ClientPocketName,
)
from freecad_mcp._shared.protocol.pocket_feature_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.pocket_feature import pocket_feature_operation


class CompletePocketFeatureDouble:
    """A test double that satisfies every pocket_feature dependency."""

    freecad = object()
    part = object()
    sketcher = object()

    def dict_to_placement(self, value: object) -> object:
        return value

    def placement_to_dict(self, value: object) -> object:
        return value

    def set_extrusion_symmetric(self, feature: object, value: bool) -> object:
        return None

    def set_feature_bool(
        self, feature: object, property_names: tuple[str, ...], value: bool
    ) -> object:
        return None

    def validate_document_invariants(self, document: PocketFeatureReadDocument) -> object:
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

    freecad = object()
    part = object()
    sketcher = object()

    def dict_to_placement(self, value: object) -> object:
        return value

    def placement_to_dict(self, value: object) -> object:
        return value

    def set_extrusion_symmetric(self, feature: object, value: bool) -> object:
        return None

    def set_feature_bool(
        self, feature: object, property_names: tuple[str, ...], value: bool
    ) -> object:
        return None

    def validate_document_invariants(self, document: PocketFeatureReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: PocketFeatureCollaborators = CompletePocketFeatureDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> PocketFeatureCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: PocketFeatureCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
feature_name = PocketName("MainPocket")
valid_request = PocketFeatureRequest(doc_name=document_name, sketch_name="Sketch", pocket_name=feature_name, length=5.0)
swapped_request = PocketFeatureRequest(
    doc_name=feature_name,  # type: ignore[arg-type]
    sketch_name="Sketch",
    pocket_name=document_name,  # type: ignore[arg-type]
    length=5.0,
)

incomplete_success: PocketFeatureSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientPocketName("MainPocket")
    assert_type(client.pocket_feature(document, "Sketch", named, 5.0), object)
    assert_type(pocket_feature_operation(client, True, "Doc", "Sketch", "Pocket", 5.0), CallToolResult)
    client.pocket_feature(named, "Sketch", document, 5.0)  # type: ignore[arg-type]
    client.pocket_feature("Doc", "Sketch", "Pocket", 5.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: PocketFeatureReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
