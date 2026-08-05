"""Late-bound method attachments for the ``FreeCADRPC`` façade."""

from __future__ import annotations

from ..methods import (
    cad_methods,
    dispatch_helpers,
    gui_methods,
    lease_methods,
    lifecycle_methods,
    v2_methods,
)
from ..methods.cad_methods_ops.recompute_helpers import collect_invalid_objects
from ..methods.cad_methods_ops.sketch_gui_constraints import (
    sketch_delete_constraint_gui,
)
from ..methods.cad_methods_ops.sketch_gui_geometry import sketch_delete_geometry_gui
from ..methods.cad_methods_ops.snapshot_restore import restore_gui, snapshot_gui


def _collect_invalid_objects(self):
    return collect_invalid_objects(self._cad_collaborators.freecad)


def _sketch_delete_constraint_gui(
    self, doc_name, sketch_name, constraint_indices, constraint_names
):
    return sketch_delete_constraint_gui(
        doc_name,
        sketch_name,
        constraint_indices,
        constraint_names,
        freecad=self._cad_collaborators.freecad,
    )


def _sketch_delete_geometry_gui(self, doc_name, sketch_name, geometry_indices):
    return sketch_delete_geometry_gui(
        doc_name,
        sketch_name,
        geometry_indices,
        freecad=self._cad_collaborators.freecad,
    )


def bind_freecad_rpc(FreeCADRPC):
    # Phase 4 slice 4H — dispatch internals (private; not XML-RPC surface)
    FreeCADRPC._current_inflight = dispatch_helpers.current_inflight
    FreeCADRPC._request_checkpoint = dispatch_helpers.request_checkpoint
    FreeCADRPC._expected_object_names = staticmethod(dispatch_helpers.expected_object_names)
    FreeCADRPC._aggregate_document_health = staticmethod(
        dispatch_helpers.aggregate_document_health
    )
    FreeCADRPC._unknown_mutation_evidence = staticmethod(
        dispatch_helpers.unknown_mutation_evidence
    )
    FreeCADRPC._observed_document_evidence = dispatch_helpers.observed_document_evidence
    FreeCADRPC._adapt_gui_mutation_result = staticmethod(
        dispatch_helpers.adapt_gui_mutation_result
    )
    FreeCADRPC._execute_mutation_with_health = dispatch_helpers.execute_mutation_with_health
    FreeCADRPC._model_credential = dispatch_helpers.model_credential
    FreeCADRPC._retain_inflight_credential = dispatch_helpers.retain_inflight_credential
    FreeCADRPC._touch_inflight_credential = dispatch_helpers.touch_inflight_credential
    FreeCADRPC._finish_cancellation_resolution = (
        dispatch_helpers.finish_cancellation_resolution
    )
    FreeCADRPC._wait_for_cancellation_resolution = (
        dispatch_helpers.wait_for_cancellation_resolution
    )
    FreeCADRPC._complete_request_cancellation = dispatch_helpers.complete_request_cancellation
    FreeCADRPC._begin_request_cancellation = dispatch_helpers.begin_request_cancellation
    FreeCADRPC._call_with_mutation_context = dispatch_helpers.call_with_mutation_context
    FreeCADRPC._dispatch = dispatch_helpers.dispatch
    FreeCADRPC._dispatch_gui = dispatch_helpers.dispatch_gui
    FreeCADRPC._dispatch_snapshot_gui = dispatch_helpers.dispatch_snapshot_gui

    # Phase 4 slice 4D — v2 protocol
    FreeCADRPC.handshake_v2 = v2_methods.handshake_v2
    FreeCADRPC._ordered_envelope_params = staticmethod(v2_methods.ordered_envelope_params)
    FreeCADRPC.invoke_v2 = v2_methods.invoke_v2
    FreeCADRPC.invoke_v2_control = v2_methods.invoke_v2_control

    # Phase 4 slice 4E — lease methods
    FreeCADRPC.lease_heartbeat_batch = lease_methods.lease_heartbeat_batch
    FreeCADRPC.lease_reconcile = lease_methods.lease_reconcile
    FreeCADRPC.claim_acquisition_result = lease_methods.claim_acquisition_result
    FreeCADRPC.acknowledge_acquisition_claim = lease_methods.acknowledge_acquisition_claim
    FreeCADRPC._start_locked_error_handoff_continuation = (
        lease_methods.start_locked_error_handoff_continuation
    )
    FreeCADRPC._journal_handoff_terminal = lease_methods.journal_handoff_terminal
    FreeCADRPC._escrow_locked_error_handoff_claim = (
        lease_methods.escrow_locked_error_handoff_claim
    )
    FreeCADRPC._run_locked_error_handoff_continuation = (
        lease_methods.run_locked_error_handoff_continuation
    )
    FreeCADRPC._acquire_document_lock_v2 = lease_methods.acquire_document_lock_v2
    FreeCADRPC.acquire_document_lock = lease_methods.acquire_document_lock
    FreeCADRPC.adopt_dirty_document = lease_methods.adopt_dirty_document
    FreeCADRPC.get_document_lock = lease_methods.get_document_lock
    FreeCADRPC.list_document_locks = lease_methods.list_document_locks
    FreeCADRPC.heartbeat_document_lock = lease_methods.heartbeat_document_lock
    FreeCADRPC.update_document_lock = lease_methods.update_document_lock
    FreeCADRPC._run_legacy_save = lease_methods.run_legacy_save
    FreeCADRPC._run_typed_save = lease_methods.run_typed_save
    FreeCADRPC.save_document = lease_methods.save_document
    FreeCADRPC.save_document_as = lease_methods.save_document_as
    FreeCADRPC.finalize_document_edit = lease_methods.finalize_document_edit
    FreeCADRPC.release_document_lock = lease_methods.release_document_lock
    FreeCADRPC.force_release_stale_lock = lease_methods.force_release_stale_lock

    # Phase 4 slice 4F — CAD methods
    FreeCADRPC.create_object = cad_methods.create_object
    FreeCADRPC.edit_object = cad_methods.edit_object
    FreeCADRPC.delete_object = cad_methods.delete_object
    FreeCADRPC.inspect_references = cad_methods.inspect_references
    FreeCADRPC.repair_references = cad_methods.repair_references
    FreeCADRPC.execute_code = cad_methods.execute_code
    FreeCADRPC.execute_code_async = cad_methods.execute_code_async
    FreeCADRPC.get_objects = cad_methods.get_objects
    FreeCADRPC.get_object = cad_methods.get_object
    FreeCADRPC.insert_part_from_library = cad_methods.insert_part_from_library
    FreeCADRPC.recompute_and_wait = cad_methods.recompute_and_wait
    FreeCADRPC.run_fem_analysis = cad_methods.run_fem_analysis
    FreeCADRPC.sketch_create = cad_methods.sketch_create
    FreeCADRPC.sketch_add_geometry = cad_methods.sketch_add_geometry
    FreeCADRPC.sketch_add_constraint = cad_methods.sketch_add_constraint
    FreeCADRPC.sketch_delete_constraint = cad_methods.sketch_delete_constraint
    FreeCADRPC.sketch_delete_geometry = cad_methods.sketch_delete_geometry
    FreeCADRPC.pad_feature = cad_methods.pad_feature
    FreeCADRPC.pocket_feature = cad_methods.pocket_feature
    FreeCADRPC.recompute_document = cad_methods.recompute_document
    FreeCADRPC.undo = cad_methods.undo
    FreeCADRPC.redo = cad_methods.redo
    FreeCADRPC.get_recompute_log = cad_methods.get_recompute_log
    FreeCADRPC.spreadsheet_create = cad_methods.spreadsheet_create
    FreeCADRPC.spreadsheet_set_cells = cad_methods.spreadsheet_set_cells
    FreeCADRPC.spreadsheet_get_cells = cad_methods.spreadsheet_get_cells
    FreeCADRPC.spreadsheet_set_alias = cad_methods.spreadsheet_set_alias
    FreeCADRPC.spreadsheet_list_aliases = cad_methods.spreadsheet_list_aliases
    FreeCADRPC.set_expression = cad_methods.set_expression
    FreeCADRPC.clear_expression = cad_methods.clear_expression
    FreeCADRPC.list_expressions = cad_methods.list_expressions
    FreeCADRPC.body_create = cad_methods.body_create
    FreeCADRPC.body_set_tip = cad_methods.body_set_tip
    FreeCADRPC.sketch_attach = cad_methods.sketch_attach
    FreeCADRPC.sketch_edit_constraint = cad_methods.sketch_edit_constraint
    FreeCADRPC.diagnose_parametric = cad_methods.diagnose_parametric
    FreeCADRPC.get_sketch_diagnostics = cad_methods.get_sketch_diagnostics
    FreeCADRPC.snapshot = cad_methods.snapshot
    FreeCADRPC.restore = cad_methods.restore
    FreeCADRPC.solve_assembly = cad_methods.solve_assembly
    FreeCADRPC._execute_code_worker = cad_methods.execute_code_worker

    # Phase 4 slice 4G — GUI / view methods
    FreeCADRPC.list_documents = gui_methods.list_documents
    FreeCADRPC.reload_document = gui_methods.reload_document
    FreeCADRPC.open_document = gui_methods.open_document
    FreeCADRPC.activate_document = gui_methods.activate_document
    FreeCADRPC.set_tree_expanded = gui_methods.set_tree_expanded
    FreeCADRPC.select_subshapes = gui_methods.select_subshapes
    FreeCADRPC.get_selection = gui_methods.get_selection
    FreeCADRPC.get_gui_state = gui_methods.get_gui_state
    FreeCADRPC.set_section_view = gui_methods.set_section_view
    FreeCADRPC.get_active_screenshot = gui_methods.get_active_screenshot
    FreeCADRPC.capture_view_sequence = gui_methods.capture_view_sequence
    FreeCADRPC.capture_view_sequence_to_disk = gui_methods.capture_view_sequence_to_disk
    FreeCADRPC.refresh_view = gui_methods.refresh_view
    FreeCADRPC.repair_view_placements = gui_methods.repair_view_placements
    FreeCADRPC.animate_placement = gui_methods.animate_placement

    # Phase 4 slice 4H — lifecycle / control-plane methods
    FreeCADRPC.get_request_status = lifecycle_methods.get_request_status
    FreeCADRPC.cancel_request = lifecycle_methods.cancel_request
    FreeCADRPC.ping = lifecycle_methods.ping
    FreeCADRPC.get_instance_info = lifecycle_methods.get_instance_info
    FreeCADRPC.check_rpc_sync = lifecycle_methods.check_rpc_sync
    FreeCADRPC.create_document = lifecycle_methods.create_document
    FreeCADRPC.get_worker_status = lifecycle_methods.get_worker_status
    FreeCADRPC.cancel_worker_job = lifecycle_methods.cancel_worker_job
    FreeCADRPC.shutdown_rpc_server = lifecycle_methods.shutdown_rpc_server
    FreeCADRPC.get_parts_list = lifecycle_methods.get_parts_list
    FreeCADRPC.close_document = lifecycle_methods.close_document
    FreeCADRPC._create_document_gui = lifecycle_methods.create_document_gui
    FreeCADRPC._reload_document_gui = lifecycle_methods.reload_document_gui
    FreeCADRPC._save_active_screenshot = lifecycle_methods.save_active_screenshot
    FreeCADRPC._close_document_gui = lifecycle_methods.close_document_gui
    FreeCADRPC._collect_invalid_objects = _collect_invalid_objects
    FreeCADRPC._sketch_delete_constraint_gui = _sketch_delete_constraint_gui
    FreeCADRPC._sketch_delete_geometry_gui = _sketch_delete_geometry_gui
    FreeCADRPC._snapshot_gui = lambda self, doc_name: snapshot_gui(doc_name)
    FreeCADRPC._restore_gui = lambda self, doc_name, snapshot_id=None: restore_gui(
        self, doc_name, snapshot_id
    )
