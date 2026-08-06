"""MCP tool registration — parametric sheet b (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    clear_expression_operation,
    list_expressions_operation,
    set_expression_operation,
    spreadsheet_list_aliases_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_spreadsheet_list_aliases(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def spreadsheet_list_aliases(
        ctx: Context,
        doc_name: str,
        sheet_name: str,
    ) -> CallToolResult:
        """List all aliases on a spreadsheet as ``{alias: address}``."""
        return spreadsheet_list_aliases_operation(
            server_connection(), server_state().only_text_feedback, doc_name, sheet_name
        )

    exports['spreadsheet_list_aliases'] = spreadsheet_list_aliases
def _register_set_expression(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def set_expression(
        ctx: Context,
        doc_name: str,
        object_name: str,
        prop_path: str,
        expression: str,
    ) -> CallToolResult:
        """Bind a FreeCAD expression to an object property.

        Common ``prop_path`` values:
        - Sketch dimensional constraints: ``Constraints[3]``
        - Pad/Pocket: ``Length``, ``Length2``

        Expression examples: ``<<Dims>>.Wall``, ``<<Dims>>.PadH``.

        Returns structured JSON; on parse/bind failure returns an error (not a
        silent Invalid object).
        """
        return set_expression_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            prop_path,
            expression,
        )

    exports['set_expression'] = set_expression
def _register_clear_expression(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def clear_expression(
        ctx: Context,
        doc_name: str,
        object_name: str,
        prop_path: str,
    ) -> CallToolResult:
        """Clear an expression binding on an object property."""
        return clear_expression_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            prop_path,
        )

    exports['clear_expression'] = clear_expression
def _register_list_expressions(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def list_expressions(
        ctx: Context,
        doc_name: str,
        object_name: str,
    ) -> CallToolResult:
        """List ExpressionEngine bindings on an object."""
        return list_expressions_operation(
            server_connection(), server_state().only_text_feedback, doc_name, object_name
        )

    exports['list_expressions'] = list_expressions

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register parametric_sheet_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_spreadsheet_list_aliases(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_set_expression(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_clear_expression(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_list_expressions(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
