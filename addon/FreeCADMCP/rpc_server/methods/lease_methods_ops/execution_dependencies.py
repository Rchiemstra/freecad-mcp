"""Explicit collaborators for dispatch, execution, and control adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .collaboration_dependencies import CompatibilityMutationAPI


@dataclass(frozen=True, slots=True)
class ExecutionCollaborators:
    """Frozen dependency graph for the transitional execution adapters.

    Optional runtime services remain explicit so startup and compatibility modes
    retain their existing fail-closed responses.  The value captures execution
    dependencies only; it owns no document, dirty, persistence, recovery,
    sidecar, credential, or collaboration policy.
    """

    compatibility_api: CompatibilityMutationAPI
    freecad: Any
    gui_dispatcher: Any | None
    worker_manager: Any | None
    snapshot_coordinator: Any
    shutdown_requested: Any
    request_replay_cache: Any | None
    inflight_request_registry: Any | None
    session_manager: Any | None
    runtime_manifest: Any | None
    actual_endpoint: dict[str, Any] | None
    runtime_id: str | None
    server_started_at: str
    addon_loaded_at: Any
    execute_timeout: float
    logger: Any
    stop_rpc_server: Callable[[], Any]
    request_identity_provider: Callable[[], Any]
    redact_rpc_diagnostic: Callable[..., str]
    lease_protocol_public_error: Callable[..., dict[str, Any]]
    generated_execute_signature: Callable[..., Any]
    validate_generated_operation_envelope: Callable[..., Any]
    snapshot_mutation_context_for_request: Callable[[], dict[str, Any]]
    create_primary_snapshot_gui: Callable[..., Any]
    freecad_version_parts: Callable[..., Any]
    load_settings: Callable[[], dict[str, Any]]
    analyze_execute_code: Callable[..., Any]
    typed_tool_warning: Callable[..., Any]
    find_gui_geometry_loop_risk: Callable[..., Any]
    find_gui_blocking_risk: Callable[..., Any]
    process_started_at: str
    boot_id: str
    profile_fingerprint: str

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")
        if self.snapshot_coordinator is None:
            raise ValueError("snapshot_coordinator collaborator is required")
        if self.shutdown_requested is None:
            raise ValueError("shutdown_requested collaborator is required")
        if float(self.execute_timeout) < 0:
            raise ValueError("execute_timeout collaborator must be non-negative")
        callables = {
            "compatibility_api.commit_compatibility_mutation": getattr(
                self.compatibility_api, "commit_compatibility_mutation", None
            ),
            "stop_rpc_server": self.stop_rpc_server,
            "request_identity_provider": self.request_identity_provider,
            "redact_rpc_diagnostic": self.redact_rpc_diagnostic,
            "lease_protocol_public_error": self.lease_protocol_public_error,
            "generated_execute_signature": self.generated_execute_signature,
            "validate_generated_operation_envelope": (
                self.validate_generated_operation_envelope
            ),
            "snapshot_mutation_context_for_request": (
                self.snapshot_mutation_context_for_request
            ),
            "create_primary_snapshot_gui": self.create_primary_snapshot_gui,
            "freecad_version_parts": self.freecad_version_parts,
            "load_settings": self.load_settings,
            "analyze_execute_code": self.analyze_execute_code,
            "typed_tool_warning": self.typed_tool_warning,
            "find_gui_geometry_loop_risk": self.find_gui_geometry_loop_risk,
            "find_gui_blocking_risk": self.find_gui_blocking_risk,
        }
        invalid = [
            name for name, collaborator in callables.items() if not callable(collaborator)
        ]
        if invalid:
            raise TypeError(
                "execution collaborators must be callable: " + ", ".join(invalid)
            )

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

    def with_authenticated_runtime(
        self,
        *,
        session_manager: Any,
        runtime_manifest: Any,
        actual_endpoint: dict[str, Any],
        server_started_at: str,
    ) -> ExecutionCollaborators:
        """Bind late authenticated values before the bridge is published."""

        if not actual_endpoint:
            raise ValueError("actual_endpoint collaborator is required")
        if not server_started_at:
            raise ValueError("server_started_at collaborator is required")
        bindings = (
            ("session_manager", self.session_manager, session_manager),
            ("runtime_manifest", self.runtime_manifest, runtime_manifest),
            ("actual_endpoint", self.actual_endpoint, actual_endpoint),
        )
        for name, current, supplied in bindings:
            if current is not None and current is not supplied:
                raise RuntimeError(f"{name} collaborator is already bound")
        if self.server_started_at and self.server_started_at != server_started_at:
            raise RuntimeError("server_started_at collaborator is already bound")
        if (
            self.session_manager is session_manager
            and self.runtime_manifest is runtime_manifest
            and self.actual_endpoint is actual_endpoint
            and self.server_started_at == server_started_at
        ):
            return self
        return replace(
            self,
            session_manager=session_manager,
            runtime_manifest=runtime_manifest,
            actual_endpoint=actual_endpoint,
            server_started_at=server_started_at,
        )

    def _without_authenticated_runtime(self) -> ExecutionCollaborators:
        """Drop adapter session handles while preserving process collaborators."""

        if (
            self.session_manager is None
            and self.runtime_manifest is None
            and self.actual_endpoint is None
            and not self.server_started_at
        ):
            return self
        return replace(
            self,
            session_manager=None,
            runtime_manifest=None,
            actual_endpoint=None,
            server_started_at="",
        )


__all__ = ["ExecutionCollaborators"]
