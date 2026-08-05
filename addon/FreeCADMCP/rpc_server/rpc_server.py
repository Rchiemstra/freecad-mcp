"""FreeCAD MCP dual-encoding RPC server façade (Phase 4 slice 4H)."""

from __future__ import annotations

# ruff: noqa: I001

import logging
import os  # §3.3 lifecycle / test shims
import platform  # §3.3 test shims
import sys  # §3.3 lifecycle shims
import threading
import uuid
from contextlib import suppress as _suppress
from datetime import UTC, datetime
from functools import partial
from pathlib import Path  # §3.3 lease runtime shims

import FreeCAD  # §3.3 test monkeypatch
import FreeCADGui  # §3.3 test monkeypatch and GUI collaborator capture
import Part as _Part
import Sketcher as _Sketcher
from PySide import QtCore, QtWidgets  # §3.3 test monkeypatch

try:
    from build_info import addon_build_id, addon_version
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.build_info import addon_build_id, addon_version

try:
    from ..collaboration_api import CollaborationAPI as _CollaborationAPI
    from ..document_lease.core_authority import (
        open_documents_mutation_capability as _open_documents_mutation_capability,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from collaboration_api import CollaborationAPI as _CollaborationAPI
    from document_lease.core_authority import (
        open_documents_mutation_capability as _open_document_scope,
    )
else:
    _open_document_scope = _open_documents_mutation_capability

from .acquisition_claims import AcquisitionClaimStore
from .commands import CommandDependencies, register_commands, schedule_toggle_sync
from .filtered_xmlrpc_server import FilteredXMLRPCServer, validate_allowed_ips  # noqa: F401
from .gui_dispatcher_qt import GuiDispatcher  # lifecycle test monkeypatch
from .gui_context_runtime import (
    render as _render_gui_context,
    restore as _restore_gui_context,
    snapshot as _snapshot_gui_context,
    store as _store_gui_context,
)
from .gui_context_snapshot import capture_baseline as _capture_gui_context_baseline
from .gui_personal_registry import PersonalViewRegistry as _PersonalViewRegistry
from .gui_animation_runtime import (
    apply_sample as _apply_personal_placement_sample,
    prepare as _prepare_personal_placement_animation,
    repair_placements as _repair_personal_placements,
    restore as _restore_personal_placement_animation,
)
from .gui_document_runtime import (
    open_document as _open_gui_document,
    reload_document as _reload_gui_document,
)
from .gui_dispatch import _flush_gui_events
from .gui_section_runtime import set_section_view as _set_named_section_view
from .handoff_continuations import HandoffContinuationStore
from .execute_code_analysis import analyze_execute_code, typed_tool_warning
from .execution_safety import find_gui_blocking_risk, find_gui_geometry_loop_risk

try:
    from ..dispatch.inflight_request_registry import InflightRequestRegistry
except ImportError:
    from dispatch.inflight_request_registry import InflightRequestRegistry
try:
    from ..dispatch.request_cancellation_error import (
        RequestCancellationError as _RequestCancellationError,
    )
except ImportError:
    from dispatch.request_cancellation_error import (
        RequestCancellationError as _RequestCancellationError,
    )

try:
    from .._shared.protocol.public_error import (
        public_error as lease_protocol_public_error,
    )
    from ..transport.authentication import (
        SessionManager,
        load_profile_secret,
        make_runtime_manifest,
    )
    from ..transport.replay import RequestReplayCache
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.public_error import (
        public_error as lease_protocol_public_error,
    )
    from transport.authentication import (
        SessionManager,
        load_profile_secret,
        make_runtime_manifest,
    )
    from transport.replay import RequestReplayCache
from .lease_runtime import (  # noqa: F401
    LeaseRuntimeCompatibility as _LeaseRuntimeCompatibility,
    LeaseRuntimeDependencies as _LeaseRuntimeDependencies,
    _boot_identity as _boot_identity_impl,
    _ensure_lease_watchdog_running as _ensure_lease_watchdog_running_impl,
    _import_document_lease,
    _import_document_lock,
    _lease_watchdog_loop as _lease_watchdog_loop_impl,
    _make_local_runtime_identity as _make_local_runtime_identity_impl,
    _probe_process_liveness as _probe_process_liveness_impl,
    _process_started_at as _process_started_at_impl,
    _profile_fingerprint as _profile_fingerprint_impl,
    _require_authenticated_lease_runtime as _require_authenticated_lease_runtime_impl,
    _trusted_boot_identity as _trusted_boot_identity_impl,
    _utc_timestamp,
    bind_lease_runtime_compatibility as _bind_lease_runtime_compatibility,
    initialize_document_lease_runtime as _initialize_document_lease_runtime_impl,
    shutdown_document_lease_runtime as _shutdown_document_lease_runtime_impl,
)
from .methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators as _CadCollaborators,
)
from .methods.gui_methods_ops.gui_dependencies import (
    GuiCollaborators as _GuiCollaborators,
)
from .methods.lease_methods_ops.collaboration_dependencies import (
    CollaborationCollaborators as _CollaborationCollaborators,
)
from .methods.lease_methods_ops.execution_dependencies import (
    ExecutionCollaborators as _ExecutionCollaborators,
)
from .methods.lease_methods_ops.lifecycle_dependencies import (
    LifecycleCollaborators as _LifecycleCollaborators,
)
from .mutation_guard_ops.validate_invariants import (
    validate_document_invariants as _validate_document_invariants,
)
try:
    from ..lock_indicator_ops.runtime_bindings import (
        LockIndicatorRuntimeBindings as _LockIndicatorRuntimeBindings,
        bind_runtime_bindings as _bind_lock_indicator_runtime,
    )
except ImportError:  # pragma: no cover - flat addon import path
    from lock_indicator_ops.runtime_bindings import (
        LockIndicatorRuntimeBindings as _LockIndicatorRuntimeBindings,
        bind_runtime_bindings as _bind_lock_indicator_runtime,
    )
from .fem_executor import run_fem_analysis as _run_fem_analysis
from .gui_tools import (
    recompute_and_wait as _recompute_and_wait,
)
from .object_factory import create_object_gui as _create_object_gui
from .parts_library import (
    configure_parts_library_path,
    insert_part_from_library as _insert_part_from_library,
)
from .placement_codec import dict_to_placement, placement_to_dict
from .property_mapper import set_object_property
from .reference_repair import (
    inspect_references_gui,
    repair_references_gui as _repair_references_gui,
)
from .serialize import serialize_object as _serialize_object
from .save_service_ops.baseline import (
    compare_serialized_file_to_baseline as _compare_serialized_file_baseline,
)
from .rpc_helpers import (  # noqa: F401 - §3.3 moved-symbol shims
    _SAVE_VALIDATION_MARKER,
    _assert_mutation_file_metadata_unchanged as _assert_mutation_file_metadata_unchanged_impl,
    _assert_never_saved_stale_continuity,
    _authorize_locked_error_handoff_gui,
    _candidate_matches_selector_target as _candidate_matches_selector_target_impl,
    _confirm_dirty_document_adoption_gui,
    _credential_for_document as _credential_for_document_impl,
    _credential_for_selector as _credential_for_selector_impl,
    _credential_from_wire as _credential_from_wire_impl,
    _discard_terminal_snapshot,
    _effective_sidecar_block as _external_scope_impl,
    _ensure_v2_document as _ensure_v2_document_impl,
    _format_identity_registration_error,
    _freecad_version_parts,
    _generated_execute_signature,
    _generated_operation_method_spec,
    _import_core_authority,
    _lease_service_error,
    _live_document_from_selector as _live_document_from_selector_impl,
    _live_validation_evidence as _live_validation_evidence_impl,
    _recovery_snapshot_intact,
    _redact_rpc_diagnostic,
    _saved_document_expectations,
    _set_extrusion_symmetric,
    _set_feature_bool,
    _snapshot_mutation_context_for_request,
    _stale_reconcile_already_recovered,
    _stale_reconcile_classify,
    _stale_reconcile_never_saved_ready,
    _stale_reconcile_saved_baseline_ready,
    _v2_status_for_context,
    _validate_generated_operation_envelope,
    _validate_saved_document_worker as _validate_saved_document_worker_impl,
)
from .rpc_helpers_ops._common import RpcHelperDependencies as _RpcHelperDependencies
from .rpc_server_ops.facade_bindings import bind_freecad_rpc
from .server_lifecycle import (
    bind_start_rpc_server_compatibility as _bind_start_compatibility,
    start_rpc_server as _start_rpc_server,
)
from .server_shutdown import (
    bind_stop_rpc_server_compatibility as _bind_stop_compatibility,
    stop_rpc_server as _stop_rpc_server,
)
from .settings import (
    DEFAULT_SETTINGS as _DEFAULT_SETTINGS,  # noqa: F401 - compatibility export
)
from .settings import (
    SettingsPolicyError,  # §3.3 test shims
    load_settings,
    resolve_rpc_bind_host,
    save_settings,
)
from .settings import (
    get_settings_path as _get_settings_path,  # noqa: F401 - compatibility export
)
from .snapshot_service import (
    create_lease_baseline_snapshot_gui,
    create_primary_snapshot_gui,
    discard_lease_baseline_snapshot,
)
from .snapshot_service_ops.recovery_paths import (
    recovery_snapshot_path as _recovery_snapshot_path,
)
from .snapshot_service_ops.restore_snapshot import (
    restore_snapshot_in_place_gui as _restore_snapshot_in_place_gui,
)
from .snapshot_service_ops.snapshot_save_context import (
    SnapshotSaveBindings as _SnapshotSaveBindings,
    bind_snapshot_save_context as _bind_snapshot_save_context,
)
from .worker_manager import WorkerManager, WorkerRuntime
from .xmlrpc_identity_handler import (
    IdentityHandlerBindings as _IdentityHandlerBindings,
    McpIdentityRequestHandler,  # noqa: F401
    bind_identity_handler as _bind_identity_handler,
)

_addon_runtime = None
_runtime_lifecycle_lock = threading.RLock()
_runtime_shutdown_claim = None
snapshot_coordinator = threading.Lock()

logger = logging.getLogger("FreeCADMCP.rpc_server")
addon_loaded_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
_ADDON_RUNTIME_ID = str(uuid.uuid4())
document_identity_service = None
document_lease_service = None
document_lease_runtime_policy = None
document_lease_runtime_mode = None
save_service = None
lease_watchdog_thread = None
lease_watchdog_stop = threading.Event()
lease_watchdog_lock = threading.RLock()
RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS = 0.5
ShutdownEvent = threading.Event  # lifecycle construction seam

_RUNTIME_COMPATIBILITY_COMPONENTS = {
    "rpc_server_thread": "listener_thread",
    "rpc_server_instance": "listener",
    "gui_dispatcher": "dispatcher",
    "worker_manager": "worker_manager",
    "shutdown_requested": "shutdown_requested",
    "rpc_session_manager": "session_manager",
    "rpc_request_replay_cache": "request_replay_cache",
    "rpc_inflight_request_registry": "inflight_requests",
    "rpc_acquisition_claim_store": "acquisition_claims",
    "rpc_handoff_continuation_store": "handoff_continuations",
    "rpc_runtime_manifest": "runtime_manifest",
    "rpc_server_actual_endpoint": "actual_endpoint",
    "rpc_server_runtime_id": "runtime_id",
    "rpc_server_started_at": "server_started_at",
}


def __getattr__(name: str):
    """Keep legacy read-only names backed by the sole published runtime."""

    component_name = _RUNTIME_COMPATIBILITY_COMPONENTS.get(name)
    if component_name is None:
        raise AttributeError(name)
    runtime = _addon_runtime
    if runtime is None:
        return "" if name in {"rpc_server_runtime_id", "rpc_server_started_at"} else None
    return getattr(runtime, component_name)

with _suppress(ImportError):
    from .property_mapper import Object  # noqa: F401


def _lease_runtime_dependencies(*, request_replay_cache=None):
    runtime = _addon_runtime
    replay_cache = (
        request_replay_cache
        if request_replay_cache is not None
        else (
            runtime.request_replay_cache
            if runtime is not None
            else None
        )
    )
    return _LeaseRuntimeDependencies(
        ensure_v2_document=_ensure_v2_document,
        document_identity_service=document_identity_service,
        document_lease_service=document_lease_service,
        document_lease_service_provider=lambda: document_lease_service,
        document_lease_runtime_policy=document_lease_runtime_policy,
        document_lease_runtime_mode=document_lease_runtime_mode,
        save_service=save_service,
        rpc_request_replay_cache=replay_cache,
        lease_watchdog_thread=lease_watchdog_thread,
        lease_watchdog_stop=lease_watchdog_stop,
        lease_watchdog_lock=lease_watchdog_lock,
        addon_loaded_at=addon_loaded_at,
        addon_runtime_id=_ADDON_RUNTIME_ID,
        runtime_id=_ADDON_RUNTIME_ID,
        ensure_watchdog_callback=(
            None
            if _ensure_lease_watchdog_running is _ROOT_ENSURE_WATCHDOG
            else _ensure_lease_watchdog_running
        ),
        watchdog_loop_callback=(
            None
            if _lease_watchdog_loop is _ROOT_WATCHDOG_LOOP
            else _lease_watchdog_loop
        ),
        probe_process_liveness_callback=(
            None
            if _probe_process_liveness is _ROOT_PROCESS_PROBE
            else _probe_process_liveness
        ),
        trusted_boot_identity_callback=(
            None
            if _trusted_boot_identity is _ROOT_BOOT_IDENTITY
            else _trusted_boot_identity
        ),
        profile_fingerprint_callback=(
            None
            if _profile_fingerprint is _ROOT_PROFILE_FINGERPRINT
            else _profile_fingerprint
        ),
        service_process_liveness_probe=_probe_process_liveness,
    )


def _store_lease_runtime_state(dependencies) -> None:
    global document_identity_service
    global document_lease_runtime_mode
    global document_lease_runtime_policy
    global document_lease_service
    global lease_watchdog_stop
    global lease_watchdog_thread
    global save_service

    document_identity_service = dependencies.document_identity_service
    document_lease_service = dependencies.document_lease_service
    document_lease_runtime_policy = dependencies.document_lease_runtime_policy
    document_lease_runtime_mode = dependencies.document_lease_runtime_mode
    save_service = dependencies.save_service
    lease_watchdog_stop = dependencies.lease_watchdog_stop
    lease_watchdog_thread = dependencies.lease_watchdog_thread


def initialize_document_lease_runtime(
    settings=None,
    *,
    _request_replay_cache=None,
):
    dependencies = _lease_runtime_dependencies(
        request_replay_cache=_request_replay_cache
    )
    try:
        return _initialize_document_lease_runtime_impl(
            settings,
            dependencies=dependencies,
        )
    finally:
        _store_lease_runtime_state(dependencies)


_ROOT_LEASE_INITIALIZER = initialize_document_lease_runtime


def shutdown_document_lease_runtime(timeout=3.0):
    dependencies = _lease_runtime_dependencies()
    try:
        return _shutdown_document_lease_runtime_impl(
            timeout,
            dependencies=dependencies,
        )
    finally:
        _store_lease_runtime_state(dependencies)


def _lease_watchdog_loop(interval_seconds=2.0, stop_event=None):
    dependencies = _lease_runtime_dependencies()
    return _lease_watchdog_loop_impl(
        interval_seconds,
        stop_event,
        dependencies=dependencies,
    )


def _ensure_lease_watchdog_running(interval_seconds=2.0):
    dependencies = _lease_runtime_dependencies()
    try:
        return _ensure_lease_watchdog_running_impl(
            interval_seconds,
            dependencies=dependencies,
        )
    finally:
        _store_lease_runtime_state(dependencies)


def _process_started_at():
    return _process_started_at_impl(dependencies=_lease_runtime_dependencies())


def _boot_identity():
    return _boot_identity_impl(dependencies=_lease_runtime_dependencies())


def _trusted_boot_identity():
    return _trusted_boot_identity_impl(dependencies=_lease_runtime_dependencies())


def _probe_process_liveness(pid):
    return _probe_process_liveness_impl(
        pid,
        dependencies=_lease_runtime_dependencies(),
    )


def _make_local_runtime_identity(settings, lease=None):
    return _make_local_runtime_identity_impl(
        settings,
        lease,
        dependencies=_lease_runtime_dependencies(),
    )


def _require_authenticated_lease_runtime(profile_id):
    return _require_authenticated_lease_runtime_impl(
        profile_id,
        dependencies=_lease_runtime_dependencies(),
    )


def _profile_fingerprint():
    return _profile_fingerprint_impl(dependencies=_lease_runtime_dependencies())


_ROOT_ENSURE_WATCHDOG = _ensure_lease_watchdog_running
_ROOT_WATCHDOG_LOOP = _lease_watchdog_loop
_ROOT_PROCESS_PROBE = _probe_process_liveness
_ROOT_BOOT_IDENTITY = _trusted_boot_identity
_ROOT_PROFILE_FINGERPRINT = _profile_fingerprint


def _current_runtime_component(name: str):
    runtime = _addon_runtime
    return getattr(runtime, name, None) if runtime is not None else None


def _rpc_helper_dependencies(*, worker_manager_value=None) -> _RpcHelperDependencies:
    return _RpcHelperDependencies(
        document_identity_service=document_identity_service,
        document_lease_service=document_lease_service,
        worker_manager=(
            _current_runtime_component("worker_manager")
            if worker_manager_value is None
            else worker_manager_value
        ),
        logger=logger,
        import_document_lock=_import_document_lock,
        import_document_lease=_import_document_lease,
        ensure_v2_document=_ensure_v2_document,
        refresh_lock_indicator=_refresh_lock_indicator,
    )


def _ensure_v2_document(document):
    return _ensure_v2_document_impl(document, _rpc_helper_dependencies())


def _candidate_matches_selector_target(candidate, selector):
    return _candidate_matches_selector_target_impl(
        candidate, selector, _rpc_helper_dependencies()
    )


def _live_document_from_selector(selector):
    return _live_document_from_selector_impl(selector, _rpc_helper_dependencies())


def _credential_from_wire(payload, identity=None):
    return _credential_from_wire_impl(
        payload, identity, dependencies=_rpc_helper_dependencies()
    )


def _credential_for_document(document_name, identity=None):
    return _credential_for_document_impl(
        document_name, identity, dependencies=_rpc_helper_dependencies()
    )


def _credential_for_selector(selector, identity=None):
    return _credential_for_selector_impl(
        selector, identity, dependencies=_rpc_helper_dependencies()
    )


def _effective_sidecar_block(document, request_identity):
    return _external_scope_impl(
        document,
        request_identity,
        dependencies=_rpc_helper_dependencies(),
    )


def _live_validation_evidence(document, document_identity, record):
    return _live_validation_evidence_impl(
        document,
        document_identity,
        record,
        _rpc_helper_dependencies(),
    )


def _assert_mutation_file_metadata_unchanged(record):
    return _assert_mutation_file_metadata_unchanged_impl(
        record, _rpc_helper_dependencies()
    )


def _validate_saved_document_worker(path, document_name, profile, expected):
    return _validate_saved_document_worker_impl(
        path,
        document_name,
        profile,
        expected,
        _rpc_helper_dependencies(),
    )


_EXECUTE_TIMEOUT = 120


def _capture_cad_collaborators(
    cad_collaborators,
    collaboration_collaborators,
    execution_collaborators,
) -> _CadCollaborators:
    if cad_collaborators is not None and not isinstance(
        cad_collaborators, _CadCollaborators
    ):
        raise TypeError("cad_collaborators must be CadCollaborators")
    if cad_collaborators is None:
        cad_collaborators = _build_cad_collaborators(
            compatibility_api=collaboration_collaborators.compatibility_api
        )
    if (
        cad_collaborators.compatibility_api
        is not collaboration_collaborators.compatibility_api
        or cad_collaborators.compatibility_api
        is not execution_collaborators.compatibility_api
    ):
        raise ValueError(
            "CAD, execution, and collaboration collaborators must share "
            "compatibility_api"
        )
    if (
        cad_collaborators.freecad is not execution_collaborators.freecad
        or cad_collaborators.freecad is not collaboration_collaborators.freecad
    ):
        raise ValueError(
            "CAD, execution, and collaboration collaborators must share freecad"
        )
    return cad_collaborators


def _dispatch_gui_collaborator(
    facade,
    callback,
    *,
    late_result_transform=None,
    journal_late_completion=True,
):
    """Preserve the façade's cancellation-aware GUI dispatch behind injection."""

    return facade._dispatch_gui(
        callback,
        late_result_transform=late_result_transform,
        journal_late_completion=journal_late_completion,
    )


def _reraise_gui_cancellation(exception):
    if isinstance(exception, _RequestCancellationError):
        raise exception


def _get_gui_request_identity(import_document_lock):
    """Resolve the request identity after document-lock initialization completes."""

    return import_document_lock().get_request_identity()


def _capture_gui_collaborators(gui_collaborators, collaboration_collaborators):
    if gui_collaborators is not None and not isinstance(
        gui_collaborators, _GuiCollaborators
    ):
        raise TypeError("gui_collaborators must be GuiCollaborators")
    if gui_collaborators is None:
        gui_collaborators = _build_gui_collaborators(
            freecad_value=collaboration_collaborators.freecad
        )
    if gui_collaborators.freecad is not collaboration_collaborators.freecad:
        raise ValueError("GUI and collaboration collaborators must share freecad")
    return gui_collaborators


def _compatibility_runtime_component(legacy_name, runtime_name, default=None):
    legacy = globals().get(legacy_name)
    if legacy is not None:
        return legacy
    runtime = _addon_runtime
    if runtime is not None:
        current = getattr(runtime, runtime_name, None)
        if current is not None:
            return current
    return default() if callable(default) else default


def _new_gateway_components():
    """Create one compatibility graph when the public façade is built directly."""

    return (
        _compatibility_runtime_component(
            "shutdown_requested", "shutdown_requested", threading.Event
        ),
        _compatibility_runtime_component(
            "rpc_request_replay_cache",
            "request_replay_cache",
            RequestReplayCache,
        ),
        _compatibility_runtime_component(
            "rpc_inflight_request_registry",
            "inflight_requests",
            InflightRequestRegistry,
        ),
        _compatibility_runtime_component(
            "rpc_acquisition_claim_store",
            "acquisition_claims",
            AcquisitionClaimStore,
        ),
        _compatibility_runtime_component(
            "rpc_handoff_continuation_store",
            "handoff_continuations",
            HandoffContinuationStore,
        ),
    )


class FreeCADRPC:
    TIMEOUT = 30
    EXECUTE_TIMEOUT = _EXECUTE_TIMEOUT
    ACQUIRE_GUI_PHASE_TIMEOUT_S = 45
    ACQUIRE_HASH_TIMEOUT_S = 30
    CLIENT_LIFECYCLE_TIMEOUT_S = 150

    def __init__(
        self,
        allow_execute_code: bool = True,
        *,
        collaboration_collaborators: _CollaborationCollaborators | None = None,
        lifecycle_collaborators: _LifecycleCollaborators | None = None,
        execution_collaborators: _ExecutionCollaborators | None = None,
        cad_collaborators: _CadCollaborators | None = None,
        gui_collaborators: _GuiCollaborators | None = None,
    ):
        self.allow_execute_code = allow_execute_code
        self._mutation_context = threading.local()
        self._inflight_context = threading.local()
        if collaboration_collaborators is not None and not isinstance(
            collaboration_collaborators, _CollaborationCollaborators
        ):
            raise TypeError(
                "collaboration_collaborators must be CollaborationCollaborators"
            )
        if execution_collaborators is not None and not isinstance(
            execution_collaborators, _ExecutionCollaborators
        ):
            raise TypeError("execution_collaborators must be ExecutionCollaborators")
        default_components = None
        if collaboration_collaborators is None or execution_collaborators is None:
            default_components = _new_gateway_components()
        if collaboration_collaborators is None:
            collaboration_collaborators = _build_collaboration_collaborators(
                runtime_manifest=(
                    execution_collaborators.runtime_manifest
                    if execution_collaborators is not None
                    else _compatibility_runtime_component(
                        "rpc_runtime_manifest", "runtime_manifest"
                    )
                ),
                inflight_request_registry=(
                    execution_collaborators.inflight_request_registry
                    if execution_collaborators is not None
                    else default_components[2]
                ),
                acquisition_claim_store=(
                    execution_collaborators.acquisition_claim_store
                    if execution_collaborators is not None
                    else default_components[3]
                ),
                handoff_continuation_store=(
                    execution_collaborators.handoff_continuation_store
                    if execution_collaborators is not None
                    else default_components[4]
                ),
                request_replay_cache=(
                    execution_collaborators.request_replay_cache
                    if execution_collaborators is not None
                    else default_components[1]
                ),
                runtime_id=_compatibility_runtime_component(
                    "rpc_server_runtime_id",
                    "runtime_id",
                    _ADDON_RUNTIME_ID,
                ),
            )
        self.__collaboration_collaborators = collaboration_collaborators
        if lifecycle_collaborators is not None and not isinstance(
            lifecycle_collaborators, _LifecycleCollaborators
        ):
            raise TypeError("lifecycle_collaborators must be LifecycleCollaborators")
        if lifecycle_collaborators is None:
            lifecycle_collaborators = _build_lifecycle_collaborators()
        self.__lifecycle_collaborators = lifecycle_collaborators
        if execution_collaborators is None:
            execution_collaborators = _build_execution_collaborators(
                compatibility_api=collaboration_collaborators.compatibility_api,
                shutdown_requested_value=default_components[0],
                request_replay_cache=collaboration_collaborators.request_replay_cache,
                inflight_request_registry=(
                    collaboration_collaborators.inflight_request_registry
                ),
                acquisition_claim_store=(
                    collaboration_collaborators.acquisition_claim_store
                ),
                handoff_continuation_store=(
                    collaboration_collaborators.handoff_continuation_store
                ),
                session_manager_value=_compatibility_runtime_component(
                    "rpc_session_manager", "session_manager"
                ),
                runtime_manifest_value=collaboration_collaborators.runtime_manifest,
                actual_endpoint_value=_compatibility_runtime_component(
                    "rpc_server_actual_endpoint", "actual_endpoint"
                ),
                runtime_id_value=collaboration_collaborators.rpc_server_runtime_id,
                server_started_at_value=_compatibility_runtime_component(
                    "rpc_server_started_at", "server_started_at", ""
                ),
            )
        if (
            execution_collaborators.compatibility_api
            is not collaboration_collaborators.compatibility_api
        ):
            raise ValueError(
                "execution and collaboration collaborators must share compatibility_api"
            )
        self.__execution_collaborators = execution_collaborators
        self.__cad_collaborators = _capture_cad_collaborators(
            cad_collaborators,
            collaboration_collaborators,
            execution_collaborators,
        )
        self.__gui_collaborators = _capture_gui_collaborators(
            gui_collaborators, collaboration_collaborators
        )

    @property
    def _collaboration_collaborators(self) -> _CollaborationCollaborators:
        return self.__collaboration_collaborators

    @property
    def _lifecycle_collaborators(self) -> _LifecycleCollaborators:
        return self.__lifecycle_collaborators

    @property
    def _execution_collaborators(self) -> _ExecutionCollaborators:
        return self.__execution_collaborators

    @property
    def _cad_collaborators(self) -> _CadCollaborators:
        return self.__cad_collaborators

    @property
    def _gui_collaborators(self) -> _GuiCollaborators:
        return self.__gui_collaborators

    def _bind_collaboration_runtime_manifest(self, runtime_manifest) -> None:
        """Complete the private graph before the listener can serve requests."""

        collaborators = self._collaboration_collaborators
        self.__collaboration_collaborators = collaborators.with_runtime_manifest(
            runtime_manifest
        )

    def _bind_authenticated_execution_runtime(
        self,
        *,
        session_manager,
        runtime_manifest,
        actual_endpoint,
        server_started_at,
    ) -> None:
        """Complete authenticated execution dependencies before publication."""

        self.__execution_collaborators = (
            self._execution_collaborators.with_authenticated_runtime(
                session_manager=session_manager,
                runtime_manifest=runtime_manifest,
                actual_endpoint=actual_endpoint,
                server_started_at=server_started_at,
            )
        )

    def _dispose_runtime_bindings(self) -> None:
        """Release restart-scoped adapter authentication references exactly once."""

        self.__collaboration_collaborators = (
            self._collaboration_collaborators._without_runtime_manifest()
        )
        self.__execution_collaborators = (
            self._execution_collaborators._without_authenticated_runtime()
        )


_RUNTIME_COMPONENT_UNSET = object()


def _resolved_runtime_component(
    supplied,
    *,
    legacy_name: str,
    runtime_name: str,
    default=None,
):
    if supplied is not _RUNTIME_COMPONENT_UNSET:
        return supplied
    return _compatibility_runtime_component(
        legacy_name,
        runtime_name,
        default,
    )


def _build_collaboration_collaborators(
    *,
    runtime_manifest=_RUNTIME_COMPONENT_UNSET,
    inflight_request_registry=_RUNTIME_COMPONENT_UNSET,
    acquisition_claim_store=_RUNTIME_COMPONENT_UNSET,
    handoff_continuation_store=_RUNTIME_COMPONENT_UNSET,
    request_replay_cache=_RUNTIME_COMPONENT_UNSET,
    runtime_id=_RUNTIME_COMPONENT_UNSET,
) -> _CollaborationCollaborators:
    """Capture the current transitional aliases at the explicit composition point."""

    return _CollaborationCollaborators(
        compatibility_api=_CollaborationAPI(document_lookup=FreeCAD.getDocument),
        freecad=FreeCAD,
        import_document_lock=_import_document_lock,
        import_document_lease=_import_document_lease,
        document_lease_service=document_lease_service,
        document_identity_service=document_identity_service,
        runtime_manifest=_resolved_runtime_component(
            runtime_manifest,
            legacy_name="rpc_runtime_manifest",
            runtime_name="runtime_manifest",
        ),
        inflight_request_registry=_resolved_runtime_component(
            inflight_request_registry,
            legacy_name="rpc_inflight_request_registry",
            runtime_name="inflight_requests",
            default=InflightRequestRegistry,
        ),
        acquisition_claim_store=_resolved_runtime_component(
            acquisition_claim_store,
            legacy_name="rpc_acquisition_claim_store",
            runtime_name="acquisition_claims",
            default=AcquisitionClaimStore,
        ),
        handoff_continuation_store=_resolved_runtime_component(
            handoff_continuation_store,
            legacy_name="rpc_handoff_continuation_store",
            runtime_name="handoff_continuations",
            default=HandoffContinuationStore,
        ),
        request_replay_cache=_resolved_runtime_component(
            request_replay_cache,
            legacy_name="rpc_request_replay_cache",
            runtime_name="request_replay_cache",
            default=RequestReplayCache,
        ),
        rpc_server_runtime_id=_resolved_runtime_component(
            runtime_id,
            legacy_name="rpc_server_runtime_id",
            runtime_name="runtime_id",
            default=_ADDON_RUNTIME_ID,
        ),
        addon_loaded_at=addon_loaded_at,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        lease_service_error=_lease_service_error,
        live_document_from_selector=_live_document_from_selector,
        confirm_dirty_document_adoption_gui=_confirm_dirty_document_adoption_gui,
        authorize_locked_error_handoff_gui=_authorize_locked_error_handoff_gui,
        create_lease_baseline_snapshot_gui=create_lease_baseline_snapshot_gui,
        discard_lease_baseline_snapshot=discard_lease_baseline_snapshot,
        credential_from_wire=_credential_from_wire,
        stale_reconcile_already_recovered=partial(
            _stale_reconcile_already_recovered,
            document_lease_service=document_lease_service,
        ),
        stale_reconcile_classify=_stale_reconcile_classify,
        assert_mutation_file_metadata_unchanged=(
            _assert_mutation_file_metadata_unchanged
        ),
        assert_never_saved_stale_continuity=partial(
            _assert_never_saved_stale_continuity,
            document_identity_service=document_identity_service,
        ),
    )


def _build_cad_collaborators(*, compatibility_api) -> _CadCollaborators:
    """Capture typed CAD dependencies at the explicit composition point."""

    return _CadCollaborators(
        compatibility_api=compatibility_api,
        freecad=FreeCAD,
        part=_Part,
        sketcher=_Sketcher,
        create_object_gui=_create_object_gui,
        insert_part_from_library=_insert_part_from_library,
        set_object_property=set_object_property,
        serialize_object=_serialize_object,
        inspect_references_gui=inspect_references_gui,
        repair_references_gui=_repair_references_gui,
        recompute_and_wait=_recompute_and_wait,
        run_fem_analysis=_run_fem_analysis,
        dict_to_placement=dict_to_placement,
        placement_to_dict=placement_to_dict,
        set_extrusion_symmetric=_set_extrusion_symmetric,
        set_feature_bool=_set_feature_bool,
        validate_document_invariants=_validate_document_invariants,
    )


def _build_gui_collaborators(*, freecad_value=None) -> _GuiCollaborators:
    """Capture GUI, presentation, and native personal-view dependencies."""

    freecad = FreeCAD if freecad_value is None else freecad_value
    return _GuiCollaborators(
        freecad=freecad,
        dispatch_gui=_dispatch_gui_collaborator,
        get_request_identity=partial(_get_gui_request_identity, _import_document_lock),
        reraise_if_cancelled=_reraise_gui_cancellation,
        document_identity_service=document_identity_service,
        ensure_v2_document=_ensure_v2_document,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        open_document=partial(_open_gui_document, freecad, FreeCADGui),
        reload_document=partial(
            _reload_gui_document,
            freecad,
            FreeCADGui,
            document_identity_service,
            document_lease_service,
            _compare_serialized_file_baseline,
        ),
        personal_view_registry=_PersonalViewRegistry(),
        set_section_view=partial(
            _set_named_section_view,
            freecad,
            FreeCADGui,
            _flush_gui_events,
        ),
        repair_placements=partial(_repair_personal_placements, freecad),
        prepare_placement_animation=partial(
            _prepare_personal_placement_animation, freecad, _Part
        ),
        apply_placement_sample=_apply_personal_placement_sample,
        restore_placement_animation=_restore_personal_placement_animation,
        store_personal_view_context=partial(_store_gui_context, FreeCADGui),
        snapshot_personal_view_context=partial(_snapshot_gui_context, FreeCADGui),
        restore_personal_view_context=partial(_restore_gui_context, FreeCADGui),
        render_personal_view_context=partial(_render_gui_context, FreeCADGui),
        snapshot_view_context=partial(_capture_gui_context_baseline, FreeCADGui),
    )


def _build_execution_collaborators(
    *,
    compatibility_api,
    gui_dispatcher_value=_RUNTIME_COMPONENT_UNSET,
    worker_manager_value=_RUNTIME_COMPONENT_UNSET,
    shutdown_requested_value=_RUNTIME_COMPONENT_UNSET,
    request_replay_cache=_RUNTIME_COMPONENT_UNSET,
    inflight_request_registry=_RUNTIME_COMPONENT_UNSET,
    acquisition_claim_store=_RUNTIME_COMPONENT_UNSET,
    handoff_continuation_store=_RUNTIME_COMPONENT_UNSET,
    session_manager_value=_RUNTIME_COMPONENT_UNSET,
    runtime_manifest_value=_RUNTIME_COMPONENT_UNSET,
    actual_endpoint_value=_RUNTIME_COMPONENT_UNSET,
    runtime_id_value=_RUNTIME_COMPONENT_UNSET,
    server_started_at_value=_RUNTIME_COMPONENT_UNSET,
) -> _ExecutionCollaborators:
    """Capture execution components at the explicit composition point."""

    return _ExecutionCollaborators(
        compatibility_api=compatibility_api,
        freecad=FreeCAD,
        gui_dispatcher=_resolved_runtime_component(
            gui_dispatcher_value,
            legacy_name="gui_dispatcher",
            runtime_name="dispatcher",
        ),
        worker_manager=_resolved_runtime_component(
            worker_manager_value,
            legacy_name="worker_manager",
            runtime_name="worker_manager",
        ),
        snapshot_coordinator=snapshot_coordinator,
        shutdown_requested=_resolved_runtime_component(
            shutdown_requested_value,
            legacy_name="shutdown_requested",
            runtime_name="shutdown_requested",
            default=threading.Event,
        ),
        request_replay_cache=_resolved_runtime_component(
            request_replay_cache,
            legacy_name="rpc_request_replay_cache",
            runtime_name="request_replay_cache",
            default=RequestReplayCache,
        ),
        inflight_request_registry=_resolved_runtime_component(
            inflight_request_registry,
            legacy_name="rpc_inflight_request_registry",
            runtime_name="inflight_requests",
            default=InflightRequestRegistry,
        ),
        acquisition_claim_store=_resolved_runtime_component(
            acquisition_claim_store,
            legacy_name="rpc_acquisition_claim_store",
            runtime_name="acquisition_claims",
            default=AcquisitionClaimStore,
        ),
        handoff_continuation_store=_resolved_runtime_component(
            handoff_continuation_store,
            legacy_name="rpc_handoff_continuation_store",
            runtime_name="handoff_continuations",
            default=HandoffContinuationStore,
        ),
        document_lease_service=document_lease_service,
        document_identity_service=document_identity_service,
        session_manager=_resolved_runtime_component(
            session_manager_value,
            legacy_name="rpc_session_manager",
            runtime_name="session_manager",
        ),
        runtime_manifest=_resolved_runtime_component(
            runtime_manifest_value,
            legacy_name="rpc_runtime_manifest",
            runtime_name="runtime_manifest",
        ),
        actual_endpoint=_resolved_runtime_component(
            actual_endpoint_value,
            legacy_name="rpc_server_actual_endpoint",
            runtime_name="actual_endpoint",
        ),
        runtime_id=_resolved_runtime_component(
            runtime_id_value,
            legacy_name="rpc_server_runtime_id",
            runtime_name="runtime_id",
            default=_ADDON_RUNTIME_ID,
        ),
        server_started_at=_resolved_runtime_component(
            server_started_at_value,
            legacy_name="rpc_server_started_at",
            runtime_name="server_started_at",
            default="",
        ),
        addon_loaded_at=addon_loaded_at,
        execute_timeout=_EXECUTE_TIMEOUT,
        logger=logger,
        stop_rpc_server=stop_rpc_server,
        import_document_lock=_import_document_lock,
        import_document_lease=_import_document_lease,
        credential_for_document=_credential_for_document,
        credential_from_wire=_credential_from_wire,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        lease_service_error=_lease_service_error,
        lease_protocol_public_error=lease_protocol_public_error,
        external_scope_block=_effective_sidecar_block,
        assert_mutation_file_metadata_unchanged=(
            _assert_mutation_file_metadata_unchanged
        ),
        generated_execute_signature=_generated_execute_signature,
        generated_operation_method_spec=_generated_operation_method_spec,
        validate_generated_operation_envelope=(_validate_generated_operation_envelope),
        snapshot_mutation_context_for_request=partial(
            _snapshot_mutation_context_for_request,
            document_lease_service=document_lease_service,
            import_document_lock=_import_document_lock,
        ),
        create_primary_snapshot_gui=create_primary_snapshot_gui,
        freecad_version_parts=_freecad_version_parts,
        load_settings=load_settings,
        analyze_execute_code=analyze_execute_code,
        typed_tool_warning=typed_tool_warning,
        find_gui_geometry_loop_risk=find_gui_geometry_loop_risk,
        find_gui_blocking_risk=find_gui_blocking_risk,
        process_started_at=_process_started_at(),
        boot_id=_boot_identity(),
        profile_fingerprint=_profile_fingerprint(),
    )


def _refresh_lock_indicator() -> None:
    """Refresh the optional GUI compatibility indicator without owning its state."""

    try:
        from ..lock_indicator import refresh_lock_indicator
    except ImportError:  # pragma: no cover - flat addon import path
        from lock_indicator import refresh_lock_indicator

    refresh_lock_indicator()


def _deprecated_force_release_result() -> dict[str, object]:
    """Return the frozen compatibility tombstone from the composition root."""

    return {
        "success": False,
        "error_code": "LOCAL_RECOVERY_REQUIRED",
        "error": (
            "Stale or malformed lease recovery is available only from "
            "FreeCAD's local document-lock UI with explicit confirmation"
        ),
    }


def _build_lifecycle_collaborators() -> _LifecycleCollaborators:
    """Capture transitional lifecycle dependencies at the composition point."""

    return _LifecycleCollaborators(
        freecad=FreeCAD,
        import_document_lock=_import_document_lock,
        import_document_lease=_import_document_lease,
        import_core_authority=_import_core_authority,
        document_lease_service=document_lease_service,
        document_identity_service=document_identity_service,
        save_service=save_service,
        credential_for_selector=_credential_for_selector,
        live_document_from_selector=_live_document_from_selector,
        ensure_v2_document=_ensure_v2_document,
        live_validation_evidence=_live_validation_evidence,
        discard_terminal_snapshot=partial(
            _discard_terminal_snapshot,
            logger_override=logger,
        ),
        saved_document_expectations=_saved_document_expectations,
        validate_saved_document_worker=_validate_saved_document_worker,
        inspect_references_gui=inspect_references_gui,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        lease_service_error=_lease_service_error,
        deprecated_force_release_result=_deprecated_force_release_result,
        refresh_lock_indicator=_refresh_lock_indicator,
    )


class _RpcRuntimeRootBindings:
    """Explicit lifecycle view over the root's restart-scoped publication state."""

    def __init__(self) -> None:
        self.QtWidgets = QtWidgets
        self.QtCore = QtCore
        self.FreeCADGui = FreeCADGui
        self.GuiDispatcher = GuiDispatcher
        self.WorkerManager = WorkerManager
        self.WorkerRuntime = WorkerRuntime
        self.FilteredXMLRPCServer = FilteredXMLRPCServer
        self.FreeCADRPC = FreeCADRPC
        self.SettingsPolicyError = SettingsPolicyError
        self.SessionManager = SessionManager
        self.RequestReplayCache = RequestReplayCache
        self.ShutdownEvent = ShutdownEvent
        self.InflightRequestRegistry = InflightRequestRegistry
        self.AcquisitionClaimStore = AcquisitionClaimStore
        self.HandoffContinuationStore = HandoffContinuationStore
        self.threading = threading
        self.sys = sys
        self.os = os
        self.Path = Path
        self.platform = platform
        self.lease_watchdog_lock = lease_watchdog_lock
        self._runtime_lifecycle_lock = _runtime_lifecycle_lock
        self._ADDON_RUNTIME_ID = _ADDON_RUNTIME_ID
        self.rpc_server_runtime_id = _ADDON_RUNTIME_ID
        self.RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS = (
            RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS
        )
        self.addon_build_id = addon_build_id
        self.addon_version = addon_version
        self.load_settings = load_settings
        self.configure_parts_library_path = configure_parts_library_path
        self.initialize_document_lease_runtime = initialize_document_lease_runtime
        self._lease_initializer_accepts_replay = (
            self.initialize_document_lease_runtime
            is _ROOT_LEASE_INITIALIZER
        )
        self.resolve_rpc_bind_host = resolve_rpc_bind_host
        self.load_profile_secret = load_profile_secret
        self.make_runtime_manifest = make_runtime_manifest
        self._freecad_version_parts = _freecad_version_parts
        self._import_document_lock = _import_document_lock
        self._import_document_lease = _import_document_lease
        self._boot_identity = _boot_identity
        self._trusted_boot_identity = _trusted_boot_identity
        self._probe_process_liveness = _probe_process_liveness
        self._make_local_runtime_identity = _make_local_runtime_identity
        self._lease_watchdog_loop = _lease_watchdog_loop
        self._ensure_lease_watchdog_running = _ensure_lease_watchdog_running
        self._profile_fingerprint = _profile_fingerprint
        self._require_authenticated_lease_runtime = (
            _require_authenticated_lease_runtime
        )
        self._ensure_v2_document = _ensure_v2_document
        self._redact_rpc_diagnostic = _redact_rpc_diagnostic
        self._build_collaboration_collaborators = (
            _build_collaboration_collaborators
        )
        self._build_cad_collaborators = _build_cad_collaborators
        self._build_gui_collaborators = _build_gui_collaborators
        self._build_execution_collaborators = _build_execution_collaborators
        self._build_lifecycle_collaborators = _build_lifecycle_collaborators

    @property
    def _addon_runtime(self):
        return _addon_runtime

    @_addon_runtime.setter
    def _addon_runtime(self, value) -> None:
        global _addon_runtime
        _addon_runtime = value

    @property
    def _runtime_shutdown_claim(self):
        return _runtime_shutdown_claim

    @_runtime_shutdown_claim.setter
    def _runtime_shutdown_claim(self, value) -> None:
        global _runtime_shutdown_claim
        _runtime_shutdown_claim = value

    @property
    def document_lease_service(self):
        return document_lease_service

    @document_lease_service.setter
    def document_lease_service(self, value) -> None:
        global document_lease_service
        document_lease_service = value

    @property
    def document_identity_service(self):
        return document_identity_service

    @document_identity_service.setter
    def document_identity_service(self, value) -> None:
        global document_identity_service
        document_identity_service = value

    @property
    def document_lease_runtime_policy(self):
        return document_lease_runtime_policy

    @document_lease_runtime_policy.setter
    def document_lease_runtime_policy(self, value) -> None:
        global document_lease_runtime_policy
        document_lease_runtime_policy = value

    @property
    def document_lease_runtime_mode(self):
        return document_lease_runtime_mode

    @document_lease_runtime_mode.setter
    def document_lease_runtime_mode(self, value) -> None:
        global document_lease_runtime_mode
        document_lease_runtime_mode = value

    @property
    def save_service(self):
        return save_service

    @save_service.setter
    def save_service(self, value) -> None:
        global save_service
        save_service = value

    @property
    def lease_watchdog_stop(self):
        return lease_watchdog_stop

    @lease_watchdog_stop.setter
    def lease_watchdog_stop(self, value) -> None:
        global lease_watchdog_stop
        lease_watchdog_stop = value

    @property
    def lease_watchdog_thread(self):
        return lease_watchdog_thread

    @lease_watchdog_thread.setter
    def lease_watchdog_thread(self, value) -> None:
        global lease_watchdog_thread
        lease_watchdog_thread = value

def start_rpc_server(port=None):
    """Start the add-on runtime through its one explicit composition path."""

    return _start_rpc_server(port=port, dependencies=_RpcRuntimeRootBindings())


def stop_rpc_server(*, wait_for_completion=False):
    """Dispose the exact runtime graph currently published by this root."""

    return _stop_rpc_server(
        dependencies=_RpcRuntimeRootBindings(),
        wait_for_completion=wait_for_completion,
    )


def runtime_running() -> bool:
    runtime = _addon_runtime
    return runtime is not None and not runtime.disposed


bind_freecad_rpc(FreeCADRPC)
_document_lock_module = _import_document_lock()
_bind_identity_handler(
    _IdentityHandlerBindings(
        set_request_identity=_document_lock_module.set_request_identity,
        clear_request_identity=_document_lock_module.clear_request_identity,
    )
)
_bind_snapshot_save_context(
    _SnapshotSaveBindings(
        begin_agent_mutation_scope=(
            _document_lock_module.begin_agent_mutation_scope
        ),
        end_agent_mutation_scope=_document_lock_module.end_agent_mutation_scope,
        begin_internal_snapshot_save_scope=(
            _document_lock_module.begin_internal_snapshot_save_scope
        ),
        end_internal_snapshot_save_scope=(
            _document_lock_module.end_internal_snapshot_save_scope
        ),
        open_documents_mutation_capability=(
            _open_document_scope
        ),
    )
)
_bind_start_compatibility(start_rpc_server)
_bind_stop_compatibility(stop_rpc_server)
_bind_lease_runtime_compatibility(
    _LeaseRuntimeCompatibility(
        initialize=initialize_document_lease_runtime,
        shutdown=shutdown_document_lease_runtime,
        watchdog_loop=_lease_watchdog_loop,
        ensure_watchdog=_ensure_lease_watchdog_running,
        process_started_at=_process_started_at,
        boot_identity=_boot_identity,
        trusted_boot_identity=_trusted_boot_identity,
        probe_process_liveness=_probe_process_liveness,
        make_local_runtime_identity=_make_local_runtime_identity,
        require_authenticated_runtime=_require_authenticated_lease_runtime,
        profile_fingerprint=_profile_fingerprint,
    )
)
_bind_lock_indicator_runtime(
    _LockIndicatorRuntimeBindings(
        freecad=FreeCAD,
        current_lease_service=lambda: document_lease_service,
        current_gui_dispatcher=lambda: _current_runtime_component("dispatcher"),
        current_save_service=lambda: save_service,
        list_compatibility_leases=_document_lock_module.list_leases,
        inspect_compatibility_lease=(
            _document_lock_module.inspect_persisted_compatibility_lease
        ),
        compatibility_process_alive=_document_lock_module.pid_alive,
        mark_compatibility_lease_user_intervened=(
            _document_lock_module.mark_user_intervened
        ),
        set_compatibility_gui_update_callback=(
            _document_lock_module.set_gui_update_callback
        ),
        recovery_snapshot_path=_recovery_snapshot_path,
        restore_snapshot_in_place_gui=_restore_snapshot_in_place_gui,
        validate_document_invariants=_validate_document_invariants,
        saved_document_expectations=_saved_document_expectations,
        validate_saved_document_worker=_validate_saved_document_worker,
        discard_terminal_snapshot=_discard_terminal_snapshot,
    )
)
register_commands(
    CommandDependencies(
        freecad=FreeCAD,
        load_settings=load_settings,
        save_settings=save_settings,
        start_rpc_server=start_rpc_server,
        stop_rpc_server=stop_rpc_server,
        runtime_running=runtime_running,
    )
)
schedule_toggle_sync()
