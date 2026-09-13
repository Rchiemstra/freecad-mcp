"""Explicit collaborators for typed CAD adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...._shared.protocol.body_create_contract import (
    BodyDocument,
    BodyReadDocument,
    DocumentName,
)
from ..lease_methods_ops.collaboration_dependencies import CompatibilityMutationAPI


@dataclass(frozen=True, slots=True)
class CadCollaborators:
    """Frozen, policy-free dependency graph for typed CAD operations."""

    compatibility_api: CompatibilityMutationAPI
    freecad: Any
    part: Any
    sketcher: Any
    create_object_gui: Callable[..., Any]
    insert_part_from_library: Callable[..., Any]
    set_object_property: Callable[..., Any]
    serialize_object: Callable[..., Any]
    inspect_references_gui: Callable[..., Any]
    repair_references_gui: Callable[..., Any]
    recompute_and_wait: Callable[..., Any]
    run_fem_analysis: Callable[..., Any]
    dict_to_placement: Callable[..., Any]
    placement_to_dict: Callable[..., Any]
    set_extrusion_symmetric: Callable[..., Any]
    set_feature_bool: Callable[..., Any]
    validate_document_invariants: Callable[..., Any]

    def __post_init__(self) -> None:
        required_objects = {
            "freecad": self.freecad,
            "part": self.part,
            "sketcher": self.sketcher,
        }
        missing = [name for name, value in required_objects.items() if value is None]
        if missing:
            raise ValueError(
                "CAD collaborators are required: " + ", ".join(missing)
            )
        callables = {
            "compatibility_api.commit_compatibility_mutation": getattr(
                self.compatibility_api, "commit_compatibility_mutation", None
            ),
            "compatibility_api.commit_native_mutation": getattr(
                self.compatibility_api, "commit_native_mutation", None
            ),
            "create_object_gui": self.create_object_gui,
            "insert_part_from_library": self.insert_part_from_library,
            "set_object_property": self.set_object_property,
            "serialize_object": self.serialize_object,
            "inspect_references_gui": self.inspect_references_gui,
            "repair_references_gui": self.repair_references_gui,
            "recompute_and_wait": self.recompute_and_wait,
            "run_fem_analysis": self.run_fem_analysis,
            "dict_to_placement": self.dict_to_placement,
            "placement_to_dict": self.placement_to_dict,
            "set_extrusion_symmetric": self.set_extrusion_symmetric,
            "set_feature_bool": self.set_feature_bool,
            "validate_document_invariants": self.validate_document_invariants,
        }
        invalid = [name for name, value in callables.items() if not callable(value)]
        if invalid:
            raise TypeError("CAD collaborators must be callable: " + ", ".join(invalid))

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[..., Any],
        *,
        structural: bool = False,
        postcondition: Callable[..., Any] | None = None,
        bind_document: bool = False,
        require_native: bool = False,
    ) -> Any:
        """Delegate exactly once through the injected native boundary."""

        if postcondition is None and not bind_document and not require_native:
            return self.compatibility_api.commit_compatibility_mutation(
                document_name, callback, structural=structural
            )
        return self.compatibility_api.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=bind_document,
            require_native=require_native,
        )

    def commit_body_create_mutation(
        self,
        document_name: DocumentName,
        callback: Callable[[BodyDocument], object],
        postcondition: Callable[[BodyReadDocument], object],
    ) -> object:
        """Delegate the Body-only contract without widening it to ``Any``."""

        return self.compatibility_api.commit_body_create_mutation(
            document_name,
            callback,
            postcondition,
        )

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
    ) -> object:
        """Delegate generic typed native commits without per-op bridge methods."""

        return self.compatibility_api.commit_native_mutation(
            document_name,
            callback,
            postcondition,
            structural=structural,
        )


__all__ = ["CadCollaborators"]
