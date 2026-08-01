"""parametric.py (thin façade; §3.3 shims)."""

from __future__ import annotations

from .parametric_ops.body_ops import (
    body_create_operation,
    body_set_tip_operation,
)
from .parametric_ops.expression_ops import (
    clear_expression_operation,
    list_expressions_operation,
    set_expression_operation,
)
from .parametric_ops.helpers import (
    _doc_missing,
    _generated_sketch_attach,
    _typed_rpc_unavailable,
    _typed_rpc_unavailable_result,
    _typed_sketch_attach_result,
)
from .parametric_ops.sketch_attach_ops import (
    diagnose_parametric_operation,
    sketch_attach_operation,
    sketch_edit_constraint_operation,
)
from .parametric_ops.spreadsheet_ops import (
    spreadsheet_create_operation,
    spreadsheet_get_cells_operation,
    spreadsheet_list_aliases_operation,
    spreadsheet_set_alias_operation,
    spreadsheet_set_cells_operation,
)

__all__ = [
    "_doc_missing",
    "_generated_sketch_attach",
    "_typed_rpc_unavailable",
    "_typed_rpc_unavailable_result",
    "_typed_sketch_attach_result",
    "body_create_operation",
    "body_set_tip_operation",
    "clear_expression_operation",
    "diagnose_parametric_operation",
    "list_expressions_operation",
    "set_expression_operation",
    "sketch_attach_operation",
    "sketch_edit_constraint_operation",
    "spreadsheet_create_operation",
    "spreadsheet_get_cells_operation",
    "spreadsheet_list_aliases_operation",
    "spreadsheet_set_alias_operation",
    "spreadsheet_set_cells_operation",
]
