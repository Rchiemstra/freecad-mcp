"""MCP tool registration — partdesign a2 (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    build_path_wire_operation,
    get_sketch_geometry_operation,
    sketch_add_external_projection_operation,
    sweep_pipe_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_get_sketch_geometry(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_sketch_geometry(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        include_constraints: bool = True,
        include_external: bool = True,
        global_coords: bool = True,
    ) -> CallToolResult:
        """Return sketch geometry endpoints, construction flags, constraints, and external refs."""
        return get_sketch_geometry_operation(
            server_connection(),
            doc_name,
            sketch_name,
            include_constraints,
            include_external,
            global_coords,
        )

    exports['get_sketch_geometry'] = get_sketch_geometry
def _register_sketch_add_external_projection(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_add_external_projection(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        source_ref: str,
        projection_mode: Literal["auto", "edge", "face", "point"] = "auto",
        defining: bool = False,
        allow_gui_geometry_loop: bool = False,
    ) -> CallToolResult:
        """Add external geometry to a sketch with assembly-aware preflight checks.

        Set ``allow_gui_geometry_loop=True`` to explicitly run the bounded preflight
        and projection mutation on FreeCAD's GUI thread. The default is false
        because the static geometry-loop guard cannot prove this generated
        preflight is bounded.
        """
        return sketch_add_external_projection_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            source_ref,
            projection_mode,
            defining,
            allow_gui_geometry_loop,
        )

    exports['sketch_add_external_projection'] = sketch_add_external_projection
def _register_build_path_wire(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def build_path_wire(
        ctx: Context,
        doc_name: str,
        wire_name: str,
        segments: list[dict[str, Any]],
        tolerance_mm: float = 0.5,
        container: str | None = None,
        if_exists: Literal["error", "skip", "replace"] = "error",
    ) -> CallToolResult:
        """Build a Part wire from sketch geometry and optional bridge segments."""
        return build_path_wire_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            wire_name,
            segments,
            tolerance_mm,
            container,
            if_exists,
        )

    exports['build_path_wire'] = build_path_wire
def _register_sweep_pipe(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sweep_pipe(
        ctx: Context,
        doc_name: str,
        path_wire: str,
        diameter_mm: float,
        solid_name: str,
        profile_mode: str = "frenet",
        color: list[float] | None = None,
        container: str | None = None,
        if_exists: Literal["error", "skip", "replace"] = "error",
    ) -> CallToolResult:
        """Sweep a circular solid pipe along a wire path."""
        return sweep_pipe_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            path_wire,
            diameter_mm,
            solid_name,
            profile_mode,
            color,
            container,
            if_exists,
        )

    exports['sweep_pipe'] = sweep_pipe

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register partdesign_a2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_get_sketch_geometry(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_add_external_projection(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_build_path_wire(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sweep_pipe(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
