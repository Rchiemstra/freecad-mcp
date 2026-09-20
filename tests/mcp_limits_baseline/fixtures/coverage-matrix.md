# Tool / workflow coverage matrix — run-20260916-mcp-limits

Legend: PASS · PASS_EXPECTED_REJECTION (PXR) · FAIL · CAPABILITY_GAP (CG) ·
OBSERVABILITY_GAP (OG) · ENVIRONMENT_ERROR (EE) · UNKNOWN_OUTCOME (UO) · NOT_TESTED (NT)

## Documents / ownership / session
| Tool | Outcome | Evidence |
|---|---|---|
| create_document | PASS | 8 documents created |
| list_documents | PASS | used repeatedly |
| close_document | PASS | StepRT, Shaft, Calib closed cleanly |
| get_document_tree | PASS | primary structural inspector; root_filter works |
| get_mutation_readiness | PASS | reports ready/undo_count/lifecycle_epoch/document_uid |
| check_rpc_sync | PASS (flaky under load) | nonce round-trip; returned "RPC failed" once immediately after a timeout, then recovered |
| open_document | CG | LEASE_PROTOCOL_REQUIRED (RPC v2) |
| reload_document / activate_document / finalize_document_edit | CG | requires_authenticated_rpc_v2 |
| acquire/release/update/list_document_lock, adopt_dirty_document, claim_acquisition_result | NT | no lease was ever refused; mutations proceeded without explicit leases in this runtime |

## Objects
| Tool | Outcome | Evidence |
|---|---|---|
| create_object (Part::Box, App::Link) | PASS | 10 boxes + 3 links/arrays |
| get_object | FAIL | succeeds with null for a missing object (D-06) |
| get_objects | OG | no projection/pagination, ~15k tokens for 10 objects (D-11) |
| edit_object | PASS | 10 length-edit cycles |
| delete_object | PASS + PXR | refuses with dependents; recursive deletes leaves-first |
| move_object | NT | |
| translate | PASS | Collar_A to x=20, verified by capture_state |
| rotate / scale / set_color | NT | |

## Spreadsheets / expressions
| Tool | Outcome | Evidence |
|---|---|---|
| spreadsheet_create | PASS | Dims, P |
| spreadsheet_set_cells | PASS (FAIL on echo) | values+aliases applied; response reports alias:null (D-12) |
| spreadsheet_set_alias | NT (covered via set_cells) | |
| spreadsheet_list_aliases | PASS | 17 aliases verified |
| spreadsheet_get_cells | NT | |
| set_expression | PASS | constraints + Pad.Length; rejects unparsable expressions |
| list_expressions | PASS | used to resolve timed-out writes |
| clear_expression | NT | |
| audit_hardcoded_dimensions | PASS | found all 8 unbound dims on Support_B |

## Sketches
| Tool | Outcome | Evidence |
|---|---|---|
| sketch_create (XY/XZ/YZ plane) | PASS | many |
| sketch_create (attach to FEATURE face) | PASS | Pad_Plate:Face6, Pad_Bowtie:Face1 |
| sketch_create (attach to BODY face) | FAIL 3/3 | 30 s hang, nothing created (D-04) |
| sketch_create (attachment_offset) | PASS | Cover sketch at z=56 |
| sketch_add_rectangle / circle / slot / polyline | PASS | incl. 50-segment polyline |
| sketch_add_constraint | PASS + PXR | 11-constraint batches; redundancy rejected atomically |
| get_sketch_diagnostics | PASS | dof, constraint counts, is_closed, fully_constrained |
| sketch_add_line/arc/ellipse/bspline/bezier/polygon/parametric_curve/import_points | NT | |
| sketch_trim/extend/split/fillet/symmetry/toggle_construction/delete_*/edit_constraint | NT | |
| sketch_add_external_projection | NT | |
| sketch_attach | NT (used sketch_create attach_to) | |

## PartDesign
| Tool | Outcome | Evidence |
|---|---|---|
| body_create | PASS | 9 bodies |
| pad_feature | PASS + PXR | blind/symmetric/strict; rejects open profile, zero length, missing sketch |
| pad_feature negative length | FAIL | silently reversed (D-08) |
| pad_feature self-intersecting profile | CG | accepted (D-07) |
| pocket_feature | PASS + PXR | through/symmetric; rejects no-material-change |
| revolve_feature | FAIL 3/3 | 'Symmetric' attribute error (D-03) |
| linear_pattern_feature | PASS | SlotRowX, propagated to added sketch geometry |
| mirror_feature | PXR | refuses to transform a pattern |
| fillet_feature | PASS + PXR | works on geometry-discovered edges; refuses all-edges and oversized radius |
| chamfer_feature | NT | |
| polar_pattern_feature | NT | |
| loft / sweep / helical_sweep / sweep_pipe / build_path_wire | NT | |
| body_set_tip | NT | |
| gears (create_spur/helical/involute, compute/check) | NT | |
| booleans (union/difference/intersection) | NT | |
| datums / binders (create_datum_plane, placement_datum, subshape_binder, placement_binder) | NT | |

## Measurement / inspection / diagnostics
| Tool | Outcome | Evidence |
|---|---|---|
| measure_volume | PASS | exact analytic agreement throughout |
| measure_volume on App::Link | FAIL | getGlobalPlacement error (D-05) |
| bounding_box | PASS | exact |
| bounding_box on App::Link | FAIL 2/2 | contradicts its own "Link-safe" docstring (D-05) |
| validate_geometry | PASS | is_valid/is_closed/check_ok/face/edge/vertex counts |
| inspect_geometry | PASS | only inspector that handles App::Link correctly |
| find_faces | PASS | plane by normal+centre; cylinder by type |
| find_edges | PASS | 4 vertical edges by direction, used to drive the fillet |
| capture_state / geometric_diff | PASS | used to verify design change #3 |
| get_recompute_log | NT (equivalent data arrives inline) | |
| diagnose_parametric / diagnose_pocket / diagnose_helix | NT | |
| inspect_references / get_dependency_graph / relink_references / repair_references / match_subshape | NT | |
| measure_distance / measure_angle / measure_area / center_of_mass / edge_axis / face_normal | NT | |
| get_global_shape / get_parts_list / compare_documents / placement_audit | NT | |
| recompute_document / recompute_and_wait | PASS | settled/idle barrier reported |

## Persistence / export
| Tool | Outcome | Evidence |
|---|---|---|
| save_document | CG | requires authenticated RPC v2 |
| save_document_as | PASS (degraded) | copy_written + sha256 + zip verification; UNAUTHENTICATED_DEGRADED_SAVE_COPY |
| save_document_copy | NT (same path as above) | |
| export_step / import_step | PASS | round-trip identical volume and bbox |
| export_stl / export_brep / import_brep | NT | |

## Recovery / history
| Tool | Outcome | Evidence |
|---|---|---|
| snapshot / restore | PASS | exact restore after a destructive recursive delete |
| undo / redo | CG | requires authenticated RPC v2 |
| run_transaction | CG (by design) | RUN_TRANSACTION_RETIRED |
| get_request_status / cancel_request / cancel_worker_job / get_worker_status | CG | v2-gated; this is what makes D-01 unrecoverable in-band |

## Assembly
| Tool | Outcome |
|---|---|
| create_assembly, create_assembly_joint, create_assembly_grounded_joint, solve_assembly, validate_movement_follow, animate_placement | NT — see REPORT §6 for why |

## View / presentation
| Tool | Outcome |
|---|---|
| get_view, get_gui_state, get_report_view, get_selection, select_subshapes, refresh_view, set_section_view, set_tree_expanded, save_view_sequence, encode_view_video, repair_view_placements | CG / NT — screenshot path returns no image in this runtime (D-10) |

## Prohibited (deliberately never called by agent choice)
`execute_code`, `execute_code_async`, `run_transaction` with agent-authored code, worker code jobs.
**Count of agent-selected arbitrary-code calls: 0.**
