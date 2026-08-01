"""Late-bound method attachments for FreeCADConnection."""

from __future__ import annotations

from .connection_init import init_connection
from .connection_methods.connection_acquisition_ops import (
    _recover_acquisition_after_transport_loss,
    _resolve_locked_error_handoff_pending,
)
from .connection_methods.connection_control_ops import (
    acknowledge_acquisition_claim,
    cancel_request,
    claim_acquisition_result,
    disconnect,
    get_request_status,
    heartbeat_document_locks_batch,
    reconcile_document_lease,
)
from .connection_methods.connection_headers_ops import (
    _refresh_headers,
    configure_lease_routing,
    configure_session_refresher,
    configure_stale_recovery,
)
from .connection_methods.connection_headers_snapshot_ops import (
    _request_headers_snapshot,
)
from .connection_methods.connection_invoke_ops import (
    _make_proxy,
    invoke_rpc,
    set_active_lease_token,
    set_identity,
)
from .connection_methods.connection_invoke_v2_ops import invoke_v2
from .connection_methods.connection_lease_ops import (
    acquire_document_lock,
    adopt_dirty_document,
    get_document_lock,
    heartbeat_document_lock,
    list_document_locks,
    update_document_lock,
)
from .connection_methods.connection_model_ops import (
    diagnose_parametric,
    recompute_document,
    redo,
    run_fem_analysis,
    sketch_attach,
    sketch_edit_constraint,
    undo,
)
from .connection_methods.connection_read_ops import (
    cancel_worker_job,
    check_rpc_sync,
    create_document,
    create_object,
    delete_object,
    edit_object,
    execute_code,
    execute_code_async,
    get_instance_info,
    get_worker_status,
    insert_part_from_library,
    inspect_references,
    ping,
    reload_document,
    repair_references,
    supports_rpc_parameter,
    verify_instance,
)
from .connection_methods.connection_save_ops import (
    finalize_document_edit,
    force_release_stale_lock,
    release_document_lock,
    save_document,
    save_document_as,
)
from .connection_methods.connection_sketch_ops import (
    pad_feature,
    pocket_feature,
    sketch_add_constraint,
    sketch_add_geometry,
    sketch_create,
    sketch_delete_constraint,
    sketch_delete_geometry,
)
from .connection_methods.connection_spreadsheet_ops import (
    body_create,
    body_set_tip,
    clear_expression,
    list_expressions,
    set_expression,
    spreadsheet_create,
    spreadsheet_get_cells,
    spreadsheet_list_aliases,
    spreadsheet_set_alias,
    spreadsheet_set_cells,
)
from .connection_methods.connection_stale_ops import (
    _handle_stale_rpc_refusal,
    _maybe_recover_stale_before_protected_rpc,
    _reconcile_stale_session,
    _retryable_stale_recovery_response,
    stale_recovery_status,
)
from .connection_methods.connection_v2_ops import (
    _build_v2_context,
    _invoke_mutation_v2,
    _unwrap_v2_response,
    _v2_lease_manager,
)
from .connection_methods.connection_view_ops import (
    activate_document,
    animate_placement,
    capture_view_sequence,
    capture_view_sequence_to_disk,
    get_active_screenshot,
    get_gui_state,
    get_object,
    get_objects,
    get_parts_list,
    get_selection,
    list_documents,
    open_document,
    recompute_and_wait,
    refresh_view,
    repair_view_placements,
    select_subshapes,
    set_section_view,
    set_tree_expanded,
)


def bind_freecad_connection(FreeCADConnection):
    def _init(self, *args, **kwargs):
        return init_connection(self, *args, **kwargs)

    FreeCADConnection.__init__ = _init

    FreeCADConnection._refresh_headers = _refresh_headers
    FreeCADConnection.configure_lease_routing = configure_lease_routing
    FreeCADConnection.configure_session_refresher = configure_session_refresher
    FreeCADConnection.configure_stale_recovery = configure_stale_recovery
    FreeCADConnection._request_headers_snapshot = _request_headers_snapshot
    FreeCADConnection.stale_recovery_status = stale_recovery_status
    FreeCADConnection._reconcile_stale_session = _reconcile_stale_session
    FreeCADConnection._maybe_recover_stale_before_protected_rpc = (
        _maybe_recover_stale_before_protected_rpc
    )
    FreeCADConnection._retryable_stale_recovery_response = (
        _retryable_stale_recovery_response
    )
    FreeCADConnection._handle_stale_rpc_refusal = _handle_stale_rpc_refusal
    FreeCADConnection._v2_lease_manager = _v2_lease_manager
    FreeCADConnection._build_v2_context = _build_v2_context
    FreeCADConnection._unwrap_v2_response = _unwrap_v2_response
    FreeCADConnection._invoke_mutation_v2 = _invoke_mutation_v2
    FreeCADConnection.set_identity = set_identity
    FreeCADConnection.set_active_lease_token = set_active_lease_token
    FreeCADConnection._make_proxy = _make_proxy
    FreeCADConnection.invoke_rpc = invoke_rpc
    FreeCADConnection.invoke_v2 = invoke_v2
    FreeCADConnection._recover_acquisition_after_transport_loss = (
        _recover_acquisition_after_transport_loss
    )
    FreeCADConnection._resolve_locked_error_handoff_pending = (
        _resolve_locked_error_handoff_pending
    )
    FreeCADConnection.heartbeat_document_locks_batch = heartbeat_document_locks_batch
    FreeCADConnection.reconcile_document_lease = reconcile_document_lease
    FreeCADConnection.get_request_status = get_request_status
    FreeCADConnection.claim_acquisition_result = claim_acquisition_result
    FreeCADConnection.acknowledge_acquisition_claim = acknowledge_acquisition_claim
    FreeCADConnection.cancel_request = cancel_request
    FreeCADConnection.disconnect = disconnect
    FreeCADConnection.ping = ping
    FreeCADConnection.check_rpc_sync = check_rpc_sync
    FreeCADConnection.get_instance_info = get_instance_info
    FreeCADConnection.supports_rpc_parameter = supports_rpc_parameter
    FreeCADConnection.verify_instance = verify_instance
    FreeCADConnection.create_document = create_document
    FreeCADConnection.create_object = create_object
    FreeCADConnection.edit_object = edit_object
    FreeCADConnection.inspect_references = inspect_references
    FreeCADConnection.repair_references = repair_references
    FreeCADConnection.delete_object = delete_object
    FreeCADConnection.reload_document = reload_document
    FreeCADConnection.insert_part_from_library = insert_part_from_library
    FreeCADConnection.execute_code = execute_code
    FreeCADConnection.get_worker_status = get_worker_status
    FreeCADConnection.cancel_worker_job = cancel_worker_job
    FreeCADConnection.execute_code_async = execute_code_async
    FreeCADConnection.get_active_screenshot = get_active_screenshot
    FreeCADConnection.capture_view_sequence = capture_view_sequence
    FreeCADConnection.capture_view_sequence_to_disk = capture_view_sequence_to_disk
    FreeCADConnection.refresh_view = refresh_view
    FreeCADConnection.repair_view_placements = repair_view_placements
    FreeCADConnection.animate_placement = animate_placement
    FreeCADConnection.get_objects = get_objects
    FreeCADConnection.get_object = get_object
    FreeCADConnection.get_parts_list = get_parts_list
    FreeCADConnection.list_documents = list_documents
    FreeCADConnection.open_document = open_document
    FreeCADConnection.activate_document = activate_document
    FreeCADConnection.set_tree_expanded = set_tree_expanded
    FreeCADConnection.select_subshapes = select_subshapes
    FreeCADConnection.get_selection = get_selection
    FreeCADConnection.get_gui_state = get_gui_state
    FreeCADConnection.recompute_and_wait = recompute_and_wait
    FreeCADConnection.set_section_view = set_section_view
    FreeCADConnection.sketch_create = sketch_create
    FreeCADConnection.sketch_add_geometry = sketch_add_geometry
    FreeCADConnection.sketch_add_constraint = sketch_add_constraint
    FreeCADConnection.sketch_delete_constraint = sketch_delete_constraint
    FreeCADConnection.sketch_delete_geometry = sketch_delete_geometry
    FreeCADConnection.pad_feature = pad_feature
    FreeCADConnection.pocket_feature = pocket_feature
    FreeCADConnection.spreadsheet_create = spreadsheet_create
    FreeCADConnection.spreadsheet_set_cells = spreadsheet_set_cells
    FreeCADConnection.spreadsheet_get_cells = spreadsheet_get_cells
    FreeCADConnection.spreadsheet_set_alias = spreadsheet_set_alias
    FreeCADConnection.spreadsheet_list_aliases = spreadsheet_list_aliases
    FreeCADConnection.set_expression = set_expression
    FreeCADConnection.clear_expression = clear_expression
    FreeCADConnection.list_expressions = list_expressions
    FreeCADConnection.body_create = body_create
    FreeCADConnection.body_set_tip = body_set_tip
    FreeCADConnection.sketch_attach = sketch_attach
    FreeCADConnection.sketch_edit_constraint = sketch_edit_constraint
    FreeCADConnection.diagnose_parametric = diagnose_parametric
    FreeCADConnection.recompute_document = recompute_document
    FreeCADConnection.undo = undo
    FreeCADConnection.redo = redo
    FreeCADConnection.run_fem_analysis = run_fem_analysis
    FreeCADConnection.acquire_document_lock = acquire_document_lock
    FreeCADConnection.adopt_dirty_document = adopt_dirty_document
    FreeCADConnection.get_document_lock = get_document_lock
    FreeCADConnection.list_document_locks = list_document_locks
    FreeCADConnection.heartbeat_document_lock = heartbeat_document_lock
    FreeCADConnection.update_document_lock = update_document_lock
    FreeCADConnection.save_document = save_document
    FreeCADConnection.save_document_as = save_document_as
    FreeCADConnection.finalize_document_edit = finalize_document_edit
    FreeCADConnection.release_document_lock = release_document_lock
    FreeCADConnection.force_release_stale_lock = force_release_stale_lock
