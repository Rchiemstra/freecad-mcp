"""FreeCAD MCP dual-encoding RPC server façade (Phase 4 slice 4H)."""

from __future__ import annotations

# ruff: noqa: I001

import logging
import hashlib
import os  # §3.3 lifecycle / test shims
import platform  # §3.3 test shims
import sys  # §3.3 lifecycle shims
import threading
import uuid
from contextlib import suppress as _suppress
from datetime import UTC, datetime
from functools import partial

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
except ImportError:  # pragma: no cover - flat addon import path
    from collaboration_api import CollaborationAPI as _CollaborationAPI

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
from . import request_identity as _request_identity
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
from .rpc_helpers_ops.feature_properties import _set_extrusion_symmetric, _set_feature_bool
from .rpc_helpers_ops.generated_execute import (
    _generated_execute_signature,
    _validate_generated_operation_envelope,
)
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
from .snapshot_service_ops.create_snapshot_bundle import create_primary_snapshot_gui
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


def _process_started_at():
    return addon_loaded_at


def _boot_identity():
    material = str(platform.node() or "local-host").encode("utf-8")
    return "host-" + hashlib.sha256(material).hexdigest()


def _profile_fingerprint():
    path = os.path.normcase(os.path.realpath(FreeCAD.getUserAppDataDir()))
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def _current_runtime_component(name: str):
    runtime = _addon_runtime
    return getattr(runtime, name, None) if runtime is not None else None


def _request_identity_provider():
    """Return the transport-only request identity provider."""

    return _request_identity


def _freecad_version_parts():
    value = getattr(FreeCAD, "Version", ())
    value = value() if callable(value) else value
    return tuple(str(part) for part in (value or ()))


def _redact_rpc_diagnostic(value, *, identity=None, inflight=None):
    del inflight
    text = str(value)
    current = _request_identity.get_request_identity() if identity is None else identity
    secrets = {str(current.get("rpc_session_token") or "")}
    for secret in secrets:
        if secret:
            text = text.replace(secret, "<redacted>")
    return text[:2048]


def _snapshot_mutation_context_for_request(*args, **kwargs):
    del args, kwargs
    return {"generations": {}, "request_id": "", "document_keys": ()}


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


def _get_gui_request_identity(identity_provider):
    """Resolve the authenticated transport identity for a GUI request."""

    return identity_provider().get_request_identity()


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
    request_replay_cache=_RUNTIME_COMPONENT_UNSET,
    runtime_id=_RUNTIME_COMPONENT_UNSET,
) -> _CollaborationCollaborators:
    """Capture the native mutation bridge and transport-only collaborators."""

    return _CollaborationCollaborators(
        compatibility_api=_CollaborationAPI(document_lookup=FreeCAD.getDocument),
        freecad=FreeCAD,
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
        get_request_identity=partial(
            _get_gui_request_identity, _request_identity_provider
        ),
        reraise_if_cancelled=_reraise_gui_cancellation,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        open_document=partial(_open_gui_document, freecad, FreeCADGui),
        reload_document=partial(_reload_gui_document, freecad, FreeCADGui),
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
    session_manager_value=_RUNTIME_COMPONENT_UNSET,
    runtime_manifest_value=_RUNTIME_COMPONENT_UNSET,
    actual_endpoint_value=_RUNTIME_COMPONENT_UNSET,
    runtime_id_value=_RUNTIME_COMPONENT_UNSET,
    server_started_at_value=_RUNTIME_COMPONENT_UNSET,
) -> _ExecutionCollaborators:
    """Capture execution components without document-authority state."""

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
        request_identity_provider=_request_identity_provider,
        redact_rpc_diagnostic=_redact_rpc_diagnostic,
        lease_protocol_public_error=lease_protocol_public_error,
        generated_execute_signature=_generated_execute_signature,
        validate_generated_operation_envelope=(_validate_generated_operation_envelope),
        snapshot_mutation_context_for_request=_snapshot_mutation_context_for_request,
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


def _build_lifecycle_collaborators() -> _LifecycleCollaborators:
    """Capture transitional lifecycle dependencies at the composition point."""

    return _LifecycleCollaborators(
        freecad=FreeCAD,
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
        self.threading = threading
        self.sys = sys
        self.os = os
        self.platform = platform
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
        self.resolve_rpc_bind_host = resolve_rpc_bind_host
        self.load_profile_secret = load_profile_secret
        self.make_runtime_manifest = make_runtime_manifest
        self._freecad_version_parts = _freecad_version_parts
        self._request_identity_provider = _request_identity_provider
        self._boot_identity = _boot_identity
        self._profile_fingerprint = _profile_fingerprint
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
_identity_provider = _request_identity_provider()
_bind_identity_handler(
    _IdentityHandlerBindings(
        set_request_identity=_identity_provider.set_request_identity,
        clear_request_identity=_identity_provider.clear_request_identity,
    )
)
_bind_start_compatibility(start_rpc_server)
_bind_stop_compatibility(stop_rpc_server)
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

__all__ = [
    "RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS",
    "FreeCADRPC",
    "runtime_running",
    "start_rpc_server",
    "stop_rpc_server",
]
