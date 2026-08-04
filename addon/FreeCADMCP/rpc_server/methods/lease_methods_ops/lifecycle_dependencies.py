"""Explicit collaborators for save, release, and lifecycle-query adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LifecycleCollaborators:
    """Frozen dependency graph for the transitional lifecycle adapters.

    Services remain explicit optional values because startup and compatibility
    modes must preserve their existing fail-closed unavailable responses.  This
    value only captures dependencies; it owns no dirty, persistence, recovery,
    credential, sidecar, or lifecycle policy.
    """

    freecad: Any
    import_document_lock: Callable[[], Any]
    import_document_lease: Callable[[], Any]
    import_core_authority: Callable[[], Any]
    document_lease_service: Any | None
    document_identity_service: Any | None
    save_service: Any | None
    credential_for_selector: Callable[..., Any]
    live_document_from_selector: Callable[..., Any]
    ensure_v2_document: Callable[..., Any]
    live_validation_evidence: Callable[..., Any]
    discard_terminal_snapshot: Callable[..., Any]
    saved_document_expectations: Callable[..., Any]
    validate_saved_document_worker: Callable[..., Any]
    inspect_references_gui: Callable[..., Any]
    redact_rpc_diagnostic: Callable[..., str]
    lease_service_error: Callable[..., dict[str, Any]]
    deprecated_force_release_result: Callable[[], dict[str, Any]]
    refresh_lock_indicator: Callable[[], Any]

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")
        callables = {
            "import_document_lock": self.import_document_lock,
            "import_document_lease": self.import_document_lease,
            "import_core_authority": self.import_core_authority,
            "credential_for_selector": self.credential_for_selector,
            "live_document_from_selector": self.live_document_from_selector,
            "ensure_v2_document": self.ensure_v2_document,
            "live_validation_evidence": self.live_validation_evidence,
            "discard_terminal_snapshot": self.discard_terminal_snapshot,
            "saved_document_expectations": self.saved_document_expectations,
            "validate_saved_document_worker": self.validate_saved_document_worker,
            "inspect_references_gui": self.inspect_references_gui,
            "redact_rpc_diagnostic": self.redact_rpc_diagnostic,
            "lease_service_error": self.lease_service_error,
            "deprecated_force_release_result": self.deprecated_force_release_result,
            "refresh_lock_indicator": self.refresh_lock_indicator,
        }
        invalid = [
            name
            for name, collaborator in callables.items()
            if not callable(collaborator)
        ]
        if invalid:
            raise TypeError(
                "lifecycle collaborators must be callable: " + ", ".join(invalid)
            )


__all__ = ["LifecycleCollaborators"]
