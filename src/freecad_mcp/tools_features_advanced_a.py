"""MCP tool registration — features advanced a (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    loft_feature_operation,
    revolve_feature_operation,
    sweep_feature_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_revolve_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def revolve_feature(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        revolve_name: str,
        angle: float = 360.0,
        axis: str = "Z_Axis",
        body_name: str | None = None,
        symmetric: bool = False,
        reversed_dir: bool = False,
    ) -> CallToolResult:
        """Revolve a closed sketch profile around an axis (PartDesign::Revolution).

        Args:
            doc_name: Document containing the sketch and body.
            sketch_name: Name of the sketch to revolve.
            revolve_name: Name for the resulting Revolution feature.
            angle: Revolution angle in degrees (default 360 = full solid of revolution).
            axis: Revolution axis. Examples: ``Z_Axis``, ``X_Axis``, ``ObjectName:Edge1``.
            body_name: Optional explicit PartDesign Body name.
            symmetric: If true, revolve symmetrically about the sketch plane.
            reversed_dir: If true, reverse the revolution direction.

        Returns:
            Success message and an isometric screenshot.
        """
        return revolve_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            revolve_name,
            angle,
            axis,
            body_name,
            symmetric,
            reversed_dir,
        )

    exports['revolve_feature'] = revolve_feature
def _register_loft_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def loft_feature(
        ctx: Context,
        doc_name: str,
        sketch_names: list[str],
        loft_name: str,
        body_name: str | None = None,
        ruled: bool = False,
        closed: bool = False,
    ) -> CallToolResult:
        """Loft through two or more sketch sections (PartDesign::AdditiveLoft).

        Args:
            doc_name: Document containing the sketches and body.
            sketch_names: Ordered list of sketch names to loft through (minimum 2).
            loft_name: Name for the resulting Loft feature.
            body_name: Optional explicit PartDesign Body name.
            ruled: If true, use straight (ruled) lofting instead of smooth.
            closed: If true, close the loft back to the first section.

        Returns:
            Success message and an isometric screenshot.
        """
        return loft_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_names,
            loft_name,
            body_name,
            ruled,
            closed,
        )

    exports['loft_feature'] = loft_feature
def _register_sweep_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sweep_feature(
        ctx: Context,
        doc_name: str,
        profile_sketch: str,
        path_sketch: str,
        sweep_name: str,
        body_name: str | None = None,
        frenet: bool = False,
    ) -> CallToolResult:
        """Sweep a profile sketch along a path sketch (PartDesign::AdditivePipe).

        Args:
            doc_name: Document containing the sketches and body.
            profile_sketch: Name of the cross-section sketch.
            path_sketch: Name of the path sketch.
            sweep_name: Name for the resulting Sweep feature.
            body_name: Optional explicit PartDesign Body name.
            frenet: If true, use Frenet-Serret frame (avoids twisting on curved paths).

        Returns:
            Success message and an isometric screenshot.
        """
        return sweep_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            profile_sketch,
            path_sketch,
            sweep_name,
            body_name,
            frenet,
        )

    exports['sweep_feature'] = sweep_feature

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register features_advanced_a MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_revolve_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_loft_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sweep_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
