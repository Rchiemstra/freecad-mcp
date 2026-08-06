"""MCP tool registration — features boolean (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    boolean_difference_operation,
    boolean_intersection_operation,
    boolean_union_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_boolean_union(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def boolean_union(
        ctx: Context,
        doc_name: str,
        shape1: str,
        shape2: str,
        result_name: str,
    ) -> CallToolResult:
        """Compute the Boolean union (fuse) of two shapes (Part::Fuse).

        Args:
            doc_name: Document containing both shapes.
            shape1: Name of the first shape object.
            shape2: Name of the second shape object.
            result_name: Name for the resulting fused shape.

        Returns:
            Success message and an isometric screenshot.
        """
        return boolean_union_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            shape1,
            shape2,
            result_name,
        )

    exports['boolean_union'] = boolean_union
def _register_boolean_difference(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def boolean_difference(
        ctx: Context,
        doc_name: str,
        shape1: str,
        shape2: str,
        result_name: str,
    ) -> CallToolResult:
        """Subtract shape2 from shape1 (Part::Cut).

        Args:
            doc_name: Document containing both shapes.
            shape1: Name of the base shape.
            shape2: Name of the tool shape to subtract.
            result_name: Name for the resulting cut shape.

        Returns:
            Success message and an isometric screenshot.
        """
        return boolean_difference_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            shape1,
            shape2,
            result_name,
        )

    exports['boolean_difference'] = boolean_difference
def _register_boolean_intersection(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def boolean_intersection(
        ctx: Context,
        doc_name: str,
        shape1: str,
        shape2: str,
        result_name: str,
    ) -> CallToolResult:
        """Compute the Boolean intersection (common) of two shapes (Part::Common).

        Args:
            doc_name: Document containing both shapes.
            shape1: Name of the first shape.
            shape2: Name of the second shape.
            result_name: Name for the resulting common shape.

        Returns:
            Success message and an isometric screenshot.
        """
        return boolean_intersection_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            shape1,
            shape2,
            result_name,
        )

    exports['boolean_intersection'] = boolean_intersection

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register features_boolean MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_boolean_union(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_boolean_difference(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_boolean_intersection(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
