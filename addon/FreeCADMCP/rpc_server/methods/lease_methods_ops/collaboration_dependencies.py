"""Explicit collaborators for acquisition, handoff, and recovery operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol


class CompatibilityMutationAPI(Protocol):
    """The narrow native compatibility-mutation bridge used by the add-on."""

    def commit_compatibility_mutation(
        self, document_name: str, callback: Callable[[], Any]
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class CollaborationCollaborators:
    """Immutable dependency set for collaboration-sensitive lease operations.

    Optional stores and services deliberately remain explicit ``None`` values so
    callers preserve the protocol's existing fail-closed unavailable responses.
    All executable collaborators are validated when the value is assembled.
    """

    compatibility_api: CompatibilityMutationAPI
    freecad: Any
    import_document_lock: Callable[[], Any]
    import_document_lease: Callable[[], Any]
    document_lease_service: Any | None
    document_identity_service: Any
    runtime_manifest: Any | None
    inflight_request_registry: Any | None
    acquisition_claim_store: Any | None
    handoff_continuation_store: Any | None
    request_replay_cache: Any | None
    rpc_server_runtime_id: str | None
    addon_loaded_at: Any
    redact_rpc_diagnostic: Callable[..., str]
    lease_service_error: Callable[..., dict[str, Any]]
    live_document_from_selector: Callable[..., Any]
    confirm_dirty_document_adoption_gui: Callable[..., bool]
    authorize_locked_error_handoff_gui: Callable[..., bool]
    create_lease_baseline_snapshot_gui: Callable[..., str]
    discard_lease_baseline_snapshot: Callable[[str], Any]
    credential_from_wire: Callable[..., Any]
    stale_reconcile_already_recovered: Callable[..., Any]
    stale_reconcile_classify: Callable[..., str]
    assert_mutation_file_metadata_unchanged: Callable[..., Any]
    assert_never_saved_stale_continuity: Callable[..., Any]

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")
        callables = {
            "compatibility_api.commit_compatibility_mutation": getattr(
                self.compatibility_api, "commit_compatibility_mutation", None
            ),
            "import_document_lock": self.import_document_lock,
            "import_document_lease": self.import_document_lease,
            "redact_rpc_diagnostic": self.redact_rpc_diagnostic,
            "lease_service_error": self.lease_service_error,
            "live_document_from_selector": self.live_document_from_selector,
            "confirm_dirty_document_adoption_gui": (
                self.confirm_dirty_document_adoption_gui
            ),
            "authorize_locked_error_handoff_gui": (
                self.authorize_locked_error_handoff_gui
            ),
            "create_lease_baseline_snapshot_gui": (
                self.create_lease_baseline_snapshot_gui
            ),
            "discard_lease_baseline_snapshot": self.discard_lease_baseline_snapshot,
            "credential_from_wire": self.credential_from_wire,
            "stale_reconcile_already_recovered": (
                self.stale_reconcile_already_recovered
            ),
            "stale_reconcile_classify": self.stale_reconcile_classify,
            "assert_mutation_file_metadata_unchanged": (
                self.assert_mutation_file_metadata_unchanged
            ),
            "assert_never_saved_stale_continuity": (
                self.assert_never_saved_stale_continuity
            ),
        }
        invalid = [name for name, collaborator in callables.items() if not callable(collaborator)]
        if invalid:
            raise TypeError(
                "collaboration collaborators must be callable: " + ", ".join(invalid)
            )

    def commit_compatibility_mutation(
        self, document_name: str, callback: Callable[[], Any]
    ) -> Any:
        """Delegate exactly once through the injected native boundary."""

        return self.compatibility_api.commit_compatibility_mutation(
            document_name, callback
        )

    def with_runtime_manifest(self, runtime_manifest: Any) -> CollaborationCollaborators:
        """Return the same dependency graph bound to its authenticated manifest."""

        if runtime_manifest is None:
            raise ValueError("runtime_manifest collaborator is required")
        if (
            self.runtime_manifest is not None
            and self.runtime_manifest is not runtime_manifest
        ):
            raise RuntimeError("runtime_manifest collaborator is already bound")
        if self.runtime_manifest is runtime_manifest:
            return self
        return replace(self, runtime_manifest=runtime_manifest)


__all__ = ["CollaborationCollaborators", "CompatibilityMutationAPI"]
