"""Explicit collaborators for GUI-facing RPC adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GuiCollaborators:
    """Immutable, policy-free dependencies used by GUI RPC adapters."""

    freecad: Any
    dispatch_gui: Callable[..., Any]
    get_request_identity: Callable[[], Any]
    reraise_if_cancelled: Callable[[BaseException], None]
    redact_rpc_diagnostic: Callable[..., str]
    open_document: Callable[[str], Any]
    reload_document: Callable[[str], Any]
    personal_view_registry: Any
    get_report_view: Callable[..., Any]
    set_section_view: Callable[..., Any]
    repair_placements: Callable[..., Any]
    prepare_placement_animation: Callable[..., Any]
    apply_placement_sample: Callable[..., Any]
    restore_placement_animation: Callable[..., Any]
    store_personal_view_context: Callable[..., Any]
    snapshot_personal_view_context: Callable[..., Any]
    restore_personal_view_context: Callable[..., Any]
    render_personal_view_context: Callable[..., Any]
    snapshot_view_context: Callable[..., Any]

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")
        callables = {
            "dispatch_gui": self.dispatch_gui,
            "get_request_identity": self.get_request_identity,
            "reraise_if_cancelled": self.reraise_if_cancelled,
            "redact_rpc_diagnostic": self.redact_rpc_diagnostic,
            "open_document": self.open_document,
            "reload_document": self.reload_document,
            "get_report_view": self.get_report_view,
            "set_section_view": self.set_section_view,
            "repair_placements": self.repair_placements,
            "prepare_placement_animation": self.prepare_placement_animation,
            "apply_placement_sample": self.apply_placement_sample,
            "restore_placement_animation": self.restore_placement_animation,
            "store_personal_view_context": self.store_personal_view_context,
            "snapshot_personal_view_context": self.snapshot_personal_view_context,
            "restore_personal_view_context": self.restore_personal_view_context,
            "render_personal_view_context": self.render_personal_view_context,
            "snapshot_view_context": self.snapshot_view_context,
        }
        invalid = [name for name, value in callables.items() if not callable(value)]
        if invalid:
            raise TypeError("GUI collaborators must be callable: " + ", ".join(invalid))
        registry_methods = (
            "activate",
            "current_target",
            "restore_target",
            "remember",
            "metadata",
        )
        if any(
            not callable(getattr(self.personal_view_registry, name, None))
            for name in registry_methods
        ):
            raise TypeError("personal_view_registry must provide actor view state")


__all__ = ["GuiCollaborators"]
