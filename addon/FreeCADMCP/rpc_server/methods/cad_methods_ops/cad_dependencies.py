"""Explicit collaborators for typed CAD adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
        callback: Callable[[], Any],
        *,
        structural: bool = False,
    ) -> Any:
        """Delegate exactly once through the injected native boundary."""

        return self.compatibility_api.commit_compatibility_mutation(
            document_name, callback, structural=structural
        )


__all__ = ["CadCollaborators"]
