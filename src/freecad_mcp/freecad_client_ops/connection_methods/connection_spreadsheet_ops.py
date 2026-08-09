"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_spreadsheet_ops as _generated,
)

spreadsheet_create = _generated.spreadsheet_create
spreadsheet_set_cells = _generated.spreadsheet_set_cells
spreadsheet_get_cells = _generated.spreadsheet_get_cells
spreadsheet_set_alias = _generated.spreadsheet_set_alias
spreadsheet_list_aliases = _generated.spreadsheet_list_aliases
set_expression = _generated.set_expression
clear_expression = _generated.clear_expression
list_expressions = _generated.list_expressions
body_create = _generated.body_create
body_set_tip = _generated.body_set_tip

__all__ = [  # noqa: RUF022
    'spreadsheet_create',
    'spreadsheet_set_cells',
    'spreadsheet_get_cells',
    'spreadsheet_set_alias',
    'spreadsheet_list_aliases',
    'set_expression',
    'clear_expression',
    'list_expressions',
    'body_create',
    'body_set_tip',
]
