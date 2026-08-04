"""FreeCAD MCP dual-encoding RPC server façade (Phase 4 slice 4H)."""
from __future__ import annotations

import logging
import os  # noqa: F401 - §3.3 lifecycle / test shims
import platform  # noqa: F401 - §3.3 test shims
import sys  # noqa: F401 - §3.3 lifecycle shims
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path  # noqa: F401 - §3.3 lease runtime shims

import FreeCAD  # noqa: F401 - §3.3 test monkeypatch
import FreeCADGui  # noqa: F401 - §3.3 test monkeypatch
from PySide import QtCore, QtWidgets  # noqa: F401 - §3.3 test monkeypatch

try:
    from build_info import addon_build_id, addon_version
except ImportError:  # pragma: no cover - flat addon import path
    from addon.FreeCADMCP.build_info import addon_build_id, addon_version  # noqa: F401

from .acquisition_claims import AcquisitionClaimStore  # noqa: I001 - frozen census lines
from .commands import register_commands, schedule_toggle_sync
from .filtered_xmlrpc_server import FilteredXMLRPCServer, validate_allowed_ips  # noqa: F401
from .gui_dispatcher_qt import GuiDispatcher  # noqa: F401 - lifecycle test monkeypatch
from .handoff_continuations import HandoffContinuationStore
try: from ..dispatch.inflight_request_registry import InflightRequestRegistry  # noqa: E701, I001 - frozen census lines
except ImportError: from dispatch.inflight_request_registry import InflightRequestRegistry  # noqa: E701, I001 - frozen census lines

try:
    from .._shared.protocol.public_error import (  # noqa: I001 - frozen census lines
        public_error as lease_protocol_public_error,
    )
    from ..transport.authentication import (
        SessionManager, load_profile_secret, make_runtime_manifest
    )
    from ..transport.replay import RequestReplayCache
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.public_error import (  # noqa: F401, I001 - frozen census lines
        public_error as lease_protocol_public_error,
    )
    from transport.authentication import (  # noqa: F401
        SessionManager, load_profile_secret, make_runtime_manifest
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
from .parts_library import configure_parts_library_path  # noqa: F401
from .reference_repair import inspect_references_gui  # noqa: F401 - §3.3 shim
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
from .server_shutdown import stop_rpc_server  # noqa: F401 - §3.3 test monkeypatch
from .settings import (
    DEFAULT_SETTINGS as _DEFAULT_SETTINGS,  # noqa: F401 - compatibility export
)
from .settings import (
    SettingsPolicyError,  # noqa: F401 - §3.3 test shims
    load_settings,  # noqa: F401 - §3.3 InitGui / test shims
    resolve_rpc_bind_host,  # noqa: F401
)
from .settings import (
    get_settings_path as _get_settings_path,  # noqa: F401 - compatibility export
)
from .snapshot_service import (  # noqa: F401 - §3.3 shims
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

try:
    from .placement_codec import dict_to_placement, placement_to_dict  # noqa: F401
    from .property_mapper import Object, set_object_property  # noqa: F401
except ImportError:  # pragma: no cover - flat addon import path
    pass


class FreeCADRPC:
    TIMEOUT = 30
    EXECUTE_TIMEOUT = 120
    ACQUIRE_GUI_PHASE_TIMEOUT_S = 45
    ACQUIRE_HASH_TIMEOUT_S = 30
    CLIENT_LIFECYCLE_TIMEOUT_S = 150

    def __init__(self, allow_execute_code: bool = True):
        self.allow_execute_code = allow_execute_code
        self._mutation_context = threading.local()
        self._inflight_context = threading.local()


bind_freecad_rpc(FreeCADRPC)
register_commands()
schedule_toggle_sync()
