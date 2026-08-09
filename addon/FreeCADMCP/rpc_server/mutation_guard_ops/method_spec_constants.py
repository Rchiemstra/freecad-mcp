"""Constants for RPC method spec construction."""

from __future__ import annotations

NATIVE_COMPATIBILITY_METHODS = frozenset(
    {
        "body_create",
        "body_set_tip",
        "clear_expression",
        "create_object",
        "delete_object",
        "edit_object",
        "insert_part_from_library",
        "pad_feature",
        "pocket_feature",
        "run_fem_analysis",
        "set_expression",
        "sketch_add_constraint",
        "sketch_add_geometry",
        "sketch_attach",
        "sketch_create",
        "sketch_delete_constraint",
        "sketch_delete_geometry",
        "sketch_edit_constraint",
        "solve_assembly",
        "spreadsheet_create",
        "spreadsheet_set_alias",
        "spreadsheet_set_cells",
    }
)


NO_OUTER_TRANSACTION = NATIVE_COMPATIBILITY_METHODS | frozenset(
    {
        "execute_code",
        "recompute_document",
        "recompute_and_wait",
        "repair_references",
        "undo",
        "redo",
        "reload_document",
        "restore",
        "close_document",
        "run_fem_analysis",
        "animate_placement",
        "repair_view_placements",
    }
)

LEASE_LIFETIME_IDEMPOTENCY_METHODS = frozenset(
    {
        "acquire_document_lock",
        "adopt_dirty_document",
        "update_document_lock",
        "lease_reconcile",
        "release_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }
)

PARTDESIGN_METHODS = frozenset(
    {
        "body_create",
        "body_set_tip",
        "sketch_create",
        "sketch_add_geometry",
        "sketch_add_constraint",
        "sketch_delete_constraint",
        "sketch_delete_geometry",
        "sketch_attach",
        "sketch_edit_constraint",
        "pad_feature",
        "pocket_feature",
    }
)

PARTIAL_ROLLBACK_METHODS = frozenset(
    {
        "export_step",
        "export_stl",
        "export_brep",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }
)

SAVE_LIFECYCLE_METHODS = frozenset(
    {"save_document", "save_document_as", "finalize_document_edit"}
)

REBIND_DOCUMENT_METHODS = frozenset(
    {"save_document_as", "finalize_document_edit", "restore", "reload_document", "close_document"}
)

FULL_VALIDATION_METHODS = frozenset({"finalize_document_edit"})
