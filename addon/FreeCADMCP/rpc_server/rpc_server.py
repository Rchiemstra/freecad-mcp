"""FreeCAD MCP dual-encoding RPC server façade (Phase 4 slice 4H)."""

from __future__ import annotations

# ruff: noqa: I001

import logging
import os  # noqa: F401 - §3.3 lifecycle / test shims
import platform  # noqa: F401 - §3.3 test shims
import sys  # noqa: F401 - §3.3 lifecycle shims
import threading
import uuid
from contextlib import suppress as _suppress
from datetime import UTC, datetime
from functools import partial
from pathlib import Path  # noqa: F401 - §3.3 lease runtime shims

import FreeCAD  # §3.3 test monkeypatch
import FreeCADGui  # §3.3 test monkeypatch and GUI collaborator capture
import Part as _Part
import Sketcher as _Sketcher
from PySide import QtCore, QtWidgets  # noqa: F401 - §3.3 test monkeypatch

try:
    from build_info import addon_build_id, addon_version
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.build_info import addon_build_id, addon_version  # noqa: F401

try:
    from ..collaboration_api import CollaborationAPI as _CollaborationAPI
except ImportError:  # pragma: no cover - flat addon import path
    from collaboration_api import CollaborationAPI as _CollaborationAPI

from .acquisition_claims import AcquisitionClaimStore
from .commands import register_commands, schedule_toggle_sync
from .filtered_xmlrpc_server import FilteredXMLRPCServer, validate_allowed_ips  # noqa: F401
from .gui_dispatcher_qt import GuiDispatcher  # noqa: F401 - lifecycle test monkeypatch
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
    from transport.authentication import (  # noqa: F401
        SessionManager,
        load_profile_secret,
        make_runtime_manifest,
    )
    from transport.replay import RequestReplayCache
from .lease_runtime import (  # noqa: F401
    _boot_identity,
    _ensure_lease_watchdog_running,
    _import_document_lease,
    _import_document_lock,
    _lease_watchdog_loop,
    _make_local_runtime_identity,
    _probe_process_liveness,
    _process_started_at,
    _profile_fingerprint,
    _require_authenticated_lease_runtime,
    _trusted_boot_identity,
    _utc_timestamp,
    initialize_document_lease_runtime,
    shutdown_document_lease_runtime,
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
from .fem_executor import run_fem_analysis as _run_fem_analysis
from .gui_tools import (
    recompute_and_wait as _recompute_and_wait,
)
from .object_factory import create_object_gui as _create_object_gui
from .parts_library import (  # noqa: F401
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
    _assert_mutation_file_metadata_unchanged,
    _assert_never_saved_stale_continuity,
    _authorize_locked_error_handoff_gui,
    _candidate_matches_selector_target,
    _confirm_dirty_document_adoption_gui,
    _credential_for_document,
    _credential_for_selector,
    _credential_from_wire,
    _discard_terminal_snapshot,
    _effective_sidecar_block,
    _ensure_v2_document,
    _format_identity_registration_error,
    _freecad_version_parts,
    _generated_execute_signature,
    _generated_operation_method_spec,
    _import_core_authority,
    _lease_service_error,
    _live_document_from_selector,
    _live_validation_evidence,
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
    _validate_saved_document_worker,
)
from .rpc_server_ops.facade_bindings import bind_freecad_rpc
from .server_lifecycle import start_rpc_server  # noqa: F401
from .server_shutdown import stop_rpc_server
from .settings import (
    DEFAULT_SETTINGS as _DEFAULT_SETTINGS,  # noqa: F401 - compatibility export
)
from .settings import (
    SettingsPolicyError,  # noqa: F401 - §3.3 test shims
    load_settings,
    resolve_rpc_bind_host,  # noqa: F401
)
from .settings import (
    get_settings_path as _get_settings_path,  # noqa: F401 - compatibility export
)
from .snapshot_service import (
    create_lease_baseline_snapshot_gui,
    create_primary_snapshot_gui,
    discard_lease_baseline_snapshot,
)
from .worker_manager import WorkerManager, WorkerRuntime  # noqa: F401
from .xmlrpc_identity_handler import McpIdentityRequestHandler  # noqa: F401

rpc_server_thread = None
rpc_server_instance = None
gui_dispatcher = None
worker_manager = None
_addon_runtime = None
snapshot_coordinator = threading.Lock()

shutdown_requested = threading.Event()
logger = logging.getLogger("FreeCADMCP.rpc_server")
addon_loaded_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
_ADDON_RUNTIME_ID = str(uuid.uuid4())
rpc_server_runtime_id = _ADDON_RUNTIME_ID
rpc_server_started_at = ""
rpc_server_actual_endpoint = None
rpc_session_manager = None
rpc_request_replay_cache = RequestReplayCache()
rpc_inflight_request_registry = InflightRequestRegistry()
rpc_acquisition_claim_store = AcquisitionClaimStore()
rpc_handoff_continuation_store = HandoffContinuationStore()
document_identity_service = None
document_lease_service = None
document_lease_runtime_policy = None
document_lease_runtime_mode = None
rpc_runtime_manifest = None
save_service = None
lease_watchdog_thread = None
lease_watchdog_stop = threading.Event()
lease_watchdog_lock = threading.RLock()
RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS = 0.5

with _suppress(ImportError):
    from .property_mapper import Object  # noqa: F401


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
        if collaboration_collaborators is None:
            collaboration_collaborators = _build_collaboration_collaborators()
        self.__collaboration_collaborators = collaboration_collaborators
        if lifecycle_collaborators is not None and not isinstance(
            lifecycle_collaborators, _LifecycleCollaborators
        ):
            raise TypeError("lifecycle_collaborators must be LifecycleCollaborators")
        if lifecycle_collaborators is None:
            lifecycle_collaborators = _build_lifecycle_collaborators()
        self.__lifecycle_collaborators = lifecycle_collaborators
        if execution_collaborators is not None and not isinstance(
            execution_collaborators, _ExecutionCollaborators
        ):
            raise TypeError("execution_collaborators must be ExecutionCollaborators")
        if execution_collaborators is None:
            execution_collaborators = _build_execution_collaborators(
                compatibility_api=collaboration_collaborators.compatibility_api
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


def _build_collaboration_collaborators() -> _CollaborationCollaborators:
    """Capture the current transitional aliases at the explicit composition point."""

    return _CollaborationCollaborators(
        compatibility_api=_CollaborationAPI(document_lookup=FreeCAD.getDocument),
        freecad=FreeCAD,
        import_document_lock=_import_document_lock,
        import_document_lease=_import_document_lease,
        document_lease_service=document_lease_service,
        document_identity_service=document_identity_service,
        runtime_manifest=rpc_runtime_manifest,
        inflight_request_registry=rpc_inflight_request_registry,
        acquisition_claim_store=rpc_acquisition_claim_store,
        handoff_continuation_store=rpc_handoff_continuation_store,
        request_replay_cache=rpc_request_replay_cache,
        rpc_server_runtime_id=_ADDON_RUNTIME_ID,
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


_EXECUTION_COMPONENT_UNSET = object()


def _build_execution_collaborators(
    *,
    compatibility_api,
    gui_dispatcher_value=_EXECUTION_COMPONENT_UNSET,
    worker_manager_value=_EXECUTION_COMPONENT_UNSET,
    request_replay_cache=_EXECUTION_COMPONENT_UNSET,
    inflight_request_registry=_EXECUTION_COMPONENT_UNSET,
    acquisition_claim_store=_EXECUTION_COMPONENT_UNSET,
    handoff_continuation_store=_EXECUTION_COMPONENT_UNSET,
    session_manager_value=_EXECUTION_COMPONENT_UNSET,
    runtime_manifest_value=_EXECUTION_COMPONENT_UNSET,
    actual_endpoint_value=_EXECUTION_COMPONENT_UNSET,
    server_started_at_value=_EXECUTION_COMPONENT_UNSET,
) -> _ExecutionCollaborators:
    """Capture execution components at the explicit composition point."""

    return _ExecutionCollaborators(
        compatibility_api=compatibility_api,
        freecad=FreeCAD,
        gui_dispatcher=(
            gui_dispatcher
            if gui_dispatcher_value is _EXECUTION_COMPONENT_UNSET
            else gui_dispatcher_value
        ),
        worker_manager=(
            worker_manager
            if worker_manager_value is _EXECUTION_COMPONENT_UNSET
            else worker_manager_value
        ),
        snapshot_coordinator=snapshot_coordinator,
        shutdown_requested=shutdown_requested,
        request_replay_cache=(
            rpc_request_replay_cache
            if request_replay_cache is _EXECUTION_COMPONENT_UNSET
            else request_replay_cache
        ),
        inflight_request_registry=(
            rpc_inflight_request_registry
            if inflight_request_registry is _EXECUTION_COMPONENT_UNSET
            else inflight_request_registry
        ),
        acquisition_claim_store=(
            rpc_acquisition_claim_store
            if acquisition_claim_store is _EXECUTION_COMPONENT_UNSET
            else acquisition_claim_store
        ),
        handoff_continuation_store=(
            rpc_handoff_continuation_store
            if handoff_continuation_store is _EXECUTION_COMPONENT_UNSET
            else handoff_continuation_store
        ),
        document_lease_service=document_lease_service,
        document_identity_service=document_identity_service,
        session_manager=(
            rpc_session_manager
            if session_manager_value is _EXECUTION_COMPONENT_UNSET
            else session_manager_value
        ),
        runtime_manifest=(
            rpc_runtime_manifest
            if runtime_manifest_value is _EXECUTION_COMPONENT_UNSET
            else runtime_manifest_value
        ),
        actual_endpoint=(
            rpc_server_actual_endpoint
            if actual_endpoint_value is _EXECUTION_COMPONENT_UNSET
            else actual_endpoint_value
        ),
        runtime_id=_ADDON_RUNTIME_ID,
        server_started_at=(
            rpc_server_started_at
            if server_started_at_value is _EXECUTION_COMPONENT_UNSET
            else server_started_at_value
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


bind_freecad_rpc(FreeCADRPC)
register_commands()
schedule_toggle_sync()
