"""MCP tool registration — features advanced b (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    chamfer_feature_operation,
    fillet_feature_operation,
    helical_sweep_feature_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_helical_sweep_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def helical_sweep_feature(
        ctx: Context,
        doc_name: str,
        profile_sketch: str,
        helix_name: str,
        pitch: float,
        height: float,
        radius: float,
        body_name: str | None = None,
        left_handed: bool = False,
        reversed_dir: bool = False,
    ) -> CallToolResult:
        """Sweep a profile along a helix (PartDesign::AdditiveHelix).

        Use this to create springs, screw threads, worm gear blanks, etc.

        Args:
            doc_name: Document containing the sketch and body.
            profile_sketch: Name of the cross-section sketch.
            helix_name: Name for the resulting Helix feature.
            pitch: Distance between successive turns in mm.
            height: Total height of the helix in mm.
            radius: Helix radius in mm.
            body_name: Optional explicit PartDesign Body name.
            left_handed: If true, produce a left-handed helix.
            reversed_dir: If true, reverse the helix direction.

        Returns:
            Success message and an isometric screenshot.
        """
        return helical_sweep_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            profile_sketch,
            helix_name,
            pitch,
            height,
            radius,
            body_name,
            left_handed,
            reversed_dir,
        )

    exports['helical_sweep_feature'] = helical_sweep_feature
def _register_fillet_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def fillet_feature(
        ctx: Context,
        doc_name: str,
        base_feature: str,
        fillet_name: str,
        radius: float,
        edge_refs: list[str] | None = None,
        body_name: str | None = None,
    ) -> CallToolResult:
        """Add a fillet to edges of an existing solid (PartDesign::Fillet).

        Args:
            doc_name: Document containing the body and feature.
            base_feature: Name of the feature to fillet.
            fillet_name: Name for the resulting Fillet feature.
            radius: Fillet radius in mm (must be > 0).
            edge_refs: Optional list of edge references like ``["Edge1","Edge3"]``.
                If omitted, all edges are filleted.
            body_name: Optional explicit PartDesign Body name.

        Returns:
            Success message and an isometric screenshot.
        """
        return fillet_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            base_feature,
            fillet_name,
            radius,
            edge_refs,
            body_name,
        )

    exports['fillet_feature'] = fillet_feature
def _register_chamfer_feature(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def chamfer_feature(
        ctx: Context,
        doc_name: str,
        base_feature: str,
        chamfer_name: str,
        size: float,
        edge_refs: list[str] | None = None,
        body_name: str | None = None,
    ) -> CallToolResult:
        """Add a chamfer to edges of an existing solid (PartDesign::Chamfer).

        Args:
            doc_name: Document containing the body and feature.
            base_feature: Name of the feature to chamfer.
            chamfer_name: Name for the resulting Chamfer feature.
            size: Chamfer size in mm (must be > 0).
            edge_refs: Optional list of edge references like ``["Edge1","Edge3"]``.
                If omitted, all edges are chamfered.
            body_name: Optional explicit PartDesign Body name.

        Returns:
            Success message and an isometric screenshot.
        """
        return chamfer_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            base_feature,
            chamfer_name,
            size,
            edge_refs,
            body_name,
        )

    exports['chamfer_feature'] = chamfer_feature

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register features_advanced_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_helical_sweep_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_fillet_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_chamfer_feature(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
