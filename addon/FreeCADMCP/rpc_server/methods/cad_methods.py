"""CAD / parametric RPC methods bound on ``FreeCADRPC``."""

from __future__ import annotations

from .cad_methods_ops.assembly import solve_assembly
from .cad_methods_ops.diagnostics import diagnose_parametric, get_sketch_diagnostics
from .cad_methods_ops.execute_code import execute_code
from .cad_methods_ops.execute_code_async import execute_code_async
from .cad_methods_ops.execute_code_worker import execute_code_worker
from .cad_methods_ops.expressions import clear_expression, list_expressions, set_expression
from .cad_methods_ops.fem_analysis import run_fem_analysis
from .cad_methods_ops.object_crud import (
    create_object,
    delete_object,
    edit_object,
    get_object,
    get_objects,
    insert_part_from_library,
)
from .cad_methods_ops.recompute_helpers import (
    get_recompute_log,
    recompute_and_wait,
    recompute_document,
    redo,
    undo,
)
from .cad_methods_ops.references import inspect_references, repair_references
from .cad_methods_ops.sketch_public import (
    body_create,
    body_set_tip,
    pad_feature,
    pocket_feature,
    sketch_add_constraint,
    sketch_add_geometry,
    sketch_attach,
    sketch_create,
    sketch_delete_constraint,
    sketch_delete_geometry,
    sketch_edit_constraint,
)
from .cad_methods_ops.snapshot_restore import restore, snapshot
from .cad_methods_ops.spreadsheet import (
    spreadsheet_create,
    spreadsheet_get_cells,
    spreadsheet_list_aliases,
    spreadsheet_set_alias,
    spreadsheet_set_cells,
)

__all__ = [
    "body_create",
    "body_set_tip",
    "clear_expression",
    "create_object",
    "delete_object",
    "diagnose_parametric",
    "edit_object",
    "execute_code",
    "execute_code_async",
    "execute_code_worker",
    "get_object",
    "get_objects",
    "get_recompute_log",
    "get_sketch_diagnostics",
    "insert_part_from_library",
    "inspect_references",
    "list_expressions",
    "pad_feature",
    "pocket_feature",
    "recompute_and_wait",
    "recompute_document",
    "redo",
    "repair_references",
    "restore",
    "run_fem_analysis",
    "set_expression",
    "sketch_add_constraint",
    "sketch_add_geometry",
    "sketch_attach",
    "sketch_create",
    "sketch_delete_constraint",
    "sketch_delete_geometry",
    "sketch_edit_constraint",
    "snapshot",
    "solve_assembly",
    "spreadsheet_create",
    "spreadsheet_get_cells",
    "spreadsheet_list_aliases",
    "spreadsheet_set_alias",
    "spreadsheet_set_cells",
    "undo",
]
