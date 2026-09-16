"""Static contract examples for the pad_feature collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import assert_type

from mcp.types import CallToolResult

from addon.FreeCADMCP._shared.protocol.pad_feature_contract import (
    DocumentName,
    PadFeatureRequest,
    PadFeatureSuccess,
    PadFeatureReadDocument,
    PadName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature import (
    PadFeatureCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from freecad_mcp._shared.protocol.pad_feature_contract import (
    PadName as ClientPadName,
)
from freecad_mcp._shared.protocol.pad_feature_contract import (
    DocumentName as ClientDocumentName,
)
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations.parametric_ops.pad_feature import pad_feature_operation


class CompletePadFeatureDouble:
    """A test double that satisfies every pad_feature dependency."""

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

    def validate_document_invariants(self, document: PadFeatureReadDocument) -> object:
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

    def validate_document_invariants(self, document: PadFeatureReadDocument) -> object:
        return None

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
    ) -> object:
        return None


complete: PadFeatureCollaborators = CompletePadFeatureDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> PadFeatureCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


missing_postcondition: PadFeatureCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
feature_name = PadName("MainPad")
valid_request = PadFeatureRequest(doc_name=document_name, sketch_name="Sketch", pad_name=feature_name, length=10.0)
swapped_request = PadFeatureRequest(
    doc_name=feature_name,  # type: ignore[arg-type]
    sketch_name="Sketch",
    pad_name=document_name,  # type: ignore[arg-type]
    length=10.0,
)

incomplete_success: PadFeatureSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}


def public_client_preserves_names(client: FreeCADConnection) -> None:
    document = ClientDocumentName("Doc")
    named = ClientPadName("MainPad")
    assert_type(client.pad_feature(document, "Sketch", named, 10.0), object)
    assert_type(pad_feature_operation(client, True, "Doc", "Sketch", "Pad", 10.0), CallToolResult)
    client.pad_feature(named, "Sketch", document, 10.0)  # type: ignore[arg-type]
    client.pad_feature("Doc", "Sketch", "Pad", 10.0)  # type: ignore[arg-type]


def postcondition_surface_is_read_only(document: PadFeatureReadDocument) -> None:
    document.addObject("App::FeaturePython", "X")  # type: ignore[attr-defined]
    document.Name = "Renamed"  # type: ignore[misc]
    item = document.getObject("X")
    if item is not None:
        item.Label = "Changed"  # type: ignore[misc]
