"""MCP tool registration — io export (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    export_brep_operation,
    export_step_operation,
    export_stl_operation,
    get_document_tree_operation,
    set_color_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_export_step(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def export_step(
        ctx: Context,
        doc_name: str,
        file_path: str,
        obj_names: list[str] | None = None,
    ) -> CallToolResult:
        """Export shapes to a STEP file.

        Args:
            doc_name: Document containing the shapes.
            file_path: Absolute path to the output STEP file.
            obj_names: Optional list of object names to export. If omitted,
                all objects with a Shape are exported.

        Returns:
            JSON with the count of exported objects and the file path.
        """
        return export_step_operation(
            server_connection(), doc_name, file_path, obj_names
        )

    exports['export_step'] = export_step
def _register_export_stl(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def export_stl(
        ctx: Context,
        doc_name: str,
        file_path: str,
        obj_names: list[str] | None = None,
        mesh_deviation: float = 0.1,
    ) -> CallToolResult:
        """Export shapes to an STL file (tessellated mesh).

        Args:
            doc_name: Document containing the shapes.
            file_path: Absolute path to the output STL file.
            obj_names: Optional list of object names. If omitted, all shapes exported.
            mesh_deviation: Tessellation accuracy in mm (smaller = finer, default 0.1).

        Returns:
            JSON with the count of exported objects, facet count, and file path.
        """
        return export_stl_operation(
            server_connection(), doc_name, file_path, obj_names, mesh_deviation
        )

    exports['export_stl'] = export_stl
def _register_export_brep(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def export_brep(
        ctx: Context,
        doc_name: str,
        obj_name: str,
        file_path: str,
    ) -> CallToolResult:
        """Export a shape to a BREP file (OpenCASCADE native format).

        BREP preserves exact geometry and is lossless for round-tripping.

        Args:
            doc_name: Document containing the shape.
            obj_name: Name of the shape object to export.
            file_path: Absolute path to the output BREP file.

        Returns:
            JSON confirming success and the file path.
        """
        return export_brep_operation(
            server_connection(), doc_name, obj_name, file_path
        )

    exports['export_brep'] = export_brep
def _register_set_color(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def set_color(
        ctx: Context,
        doc_name: str,
        obj_name: str,
        r: float,
        g: float,
        b: float,
        transparency: float = 0.0,
    ) -> CallToolResult:
        """Set the display colour and transparency of an object.

        Args:
            doc_name: Document containing the object.
            obj_name: Name of the object.
            r: Red channel 0.0-1.0.
            g: Green channel 0.0-1.0.
            b: Blue channel 0.0-1.0.
            transparency: Transparency 0.0 (opaque) - 1.0 (fully transparent).

        Returns:
            Success message and a screenshot.
        """
        return set_color_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_name,
            r,
            g,
            b,
            transparency,
        )

    exports['set_color'] = set_color
def _register_get_document_tree(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_document_tree(
        ctx: Context,
        doc_name: str,
        root_filter: str | None = None,
        max_depth: int = 4,
        include: list[str] | None = None,
        include_properties: list[str] | None = None,
        selected_nodes: list[str] | None = None,
    ) -> CallToolResult:
        """Return a compact document/container tree.

        Args:
            doc_name: Document to inspect.
            root_filter: Optional Name/Label substring used to select tree roots.
            max_depth: Maximum container depth to include.
            include: Fields to include, defaulting to Name/Label/TypeId/Visibility/State.
            include_properties: Optional object properties to include.
            selected_nodes: Names/labels whose properties should be included.

        Returns:
            JSON tree for compact agent inspection.
        """
        return get_document_tree_operation(
            server_connection(),
            doc_name,
            root_filter,
            max_depth,
            include,
            include_properties,
            selected_nodes,
        )

    exports['get_document_tree'] = get_document_tree

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register io_export MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_export_step(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_export_stl(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_export_brep(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_set_color(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_get_document_tree(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
