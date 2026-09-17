# Findings log (chronological, run-20260916-mcp-limits)

## F-01 ENVIRONMENT_ERROR / CAPABILITY_GAP — RPC protocol mismatch disables 21 tools
get_runtime_info: compatibility.compatible=false, "RPC protocol mismatch: MCP=2, addon=1".
unavailable_tools (requires_authenticated_rpc_v2): activate_document, animate_placement, cancel_request,
capture_view_sequence, capture_view_sequence_to_disk, finalize_document_edit, get_active_screenshot,
get_gui_state, get_report_view, get_request_status, get_selection, open_document, redo, refresh_view,
reload_document, repair_view_placements, save_document, select_subshapes, set_section_view,
set_tree_expanded, undo.
Verified live:
- save_document      -> "This operation requires authenticated RPC v2"
- open_document      -> rejected, error_code LEASE_PROTOCOL_REQUIRED
- undo               -> "This operation requires authenticated RPC v2"
Consequence: save / close / reopen round-trip and undo-redo recovery are IMPOSSIBLE through MCP in this
runtime. save_document_as degrades to save-a-copy (honest warning, see F-03).

## F-02 (HIGH) FAIL — 30 s GUI timeout reports failure for mutations that actually committed
Symptom: tool returns status "failed", message "Timed out after 30.0s waiting for FreeCAD GUI response
while executing; execution continues in FreeCAD ...". Independent inspection afterwards shows the
mutation WAS applied in 4 of 5 observed cases.
Observed cases:
 T1 sketch_create(attach_to="Plate:Face6")      -> timeout, NOT applied (no S_Hole in tree)
 T2 sketch_add_constraint(Horizontal geo2)      -> timeout, APPLIED (constraint_count 11 -> 12, dof 0)
 T3 set_expression(S_SupA.Constraints.sup_w)    -> timeout, APPLIED (list_expressions shows binding)
 T4 set_expression(S_SupA.Constraints.sup_z0)   -> timeout, APPLIED
 T5 set_expression(Pad_SupA.Length)             -> timeout, APPLIED
Impact: any retry-on-failure client double-applies mutations. get_request_status and cancel_request are
unavailable in this runtime (F-01), so the documented "use request status after a timeout" recovery path
does not exist -> OBSERVABILITY_GAP. Only per-object re-inspection resolves the outcome.
Also: the first check_rpc_sync immediately after T2 returned "RPC failed"; the second succeeded.

## F-03 PASS (degraded, honest) — save_document_as writes a verified copy
warning_code UNAUTHENTICATED_DEGRADED_SAVE_COPY, effective_operation save_document_copy,
canonical_savepoint_changed=false, durability_verified=true with sha256 + zip member check.
File: models/MCPLimit_Calib.FCStd sha256 31a862d9b95407e66cf71d6de8ea2d6076a6fbba12d51b0896188edb3c20369a

## F-04 OBSERVABILITY_GAP — transactions/rollback not active
Every mutation response carries transaction.status="unavailable", enabled=false, rollback_policy="none",
transaction_coverage "partial"/"unavailable". Documented per-tool transactional rollback is therefore not
in force; observed atomicity came from FreeCAD's own recompute rejection, not from MCP transactions.
Despite that, all observed rejections left NO partial objects (verified by get_document_tree).

## F-05 OBSERVABILITY_GAP — build identity not tied to a commit
get_runtime_info -> mcp.git_commit "unknown", git_dirty null, build_id "freecad-mcp-0.2.0+unknown",
profile.instance_id "unknown". Runtime-to-checkout binding had to be established out of band
(/proc/<pid>/exe -> /home/msi/FreeCAD/build/release/bin/FreeCAD).

## F-06 LOW FAIL — spreadsheet_set_cells reports alias:null for aliases it did set
First call set 4 aliases via "set_alias"; response listed {"address":"B1","alias":null} for every cell.
spreadsheet_list_aliases proved all 4 aliases exist. Response payload is misleading.
(When addressing by "alias" instead, the echo is correct.)

## F-07 OBSERVABILITY_GAP — no view capture
Every pad/pocket returns presentation_warning "Screenshot capture returned no image after the feature
committed." get_active_screenshot / get_view path is unavailable under rpc v1 -> no visual evidence.

## F-08 INFO — dedicated tools are internally implemented as generated Python
Telemetry field execution_category = "generated_internal_execute" on spreadsheet_list_aliases,
get_sketch_diagnostics, find_faces, measure_volume, bounding_box, validate_geometry, get_document_tree,
export_step, import_step, sketch_add_*, linear_pattern_feature, ... with code_sha256 and call_families.
Read-only inspectors run "mode":"worker" against a read-only snapshot; mutators run "mode":"gui".
Permitted by the campaign rules (internal templates behind a dedicated action) but recorded: MCP action
coverage here is NOT evidence of native-RPC implementation.

## F-09 PASS_EXPECTED_REJECTION — mirror of a pattern refused
mirror_feature(feature_name="SlotRowX") -> "Only additive and subtractive features can be transformed".
Matches FreeCAD semantics; no orphan SlotMirrorY left (tree verified).

## F-10 PASS_EXPECTED_REJECTION — stale document handle
After close_document("MCPLimit_StepRT"), get_object on it -> NameError: Unknown document.
Clean refusal, but surfaced as a raw Python NameError string with error_code=null (typing nit).

## F-11 FAIL — sketch attach to a Body-level face hangs; feature-level face works
sketch_create(attach_to="Plate:Face6")      -> 30 s GUI timeout, nothing created.
sketch_create(attach_to="Pad_Plate:Face6")  -> succeeded immediately (same face).
find_faces was run on the Body ("Plate") and returns Face6, so the interface invites the failing form.
