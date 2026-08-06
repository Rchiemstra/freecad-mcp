"""MCP tool registration — gui view b (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    animate_placement_operation,
    refresh_view_operation,
    repair_view_placements_operation,
)
from .responses import tool_fail
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_refresh_view(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def refresh_view(
        ctx: Context,
        focus_objects: list[str] | None = None,
        focus_object: str | None = None,
        touch_objects: list[str] | None = None,
        fit: bool = False,
        capture: bool = False,
        view_name: Literal[
            "Isometric",
            "Front",
            "Top",
            "Right",
            "Back",
            "Left",
            "Bottom",
            "Dimetric",
            "Trimetric",
        ] = "Isometric",
    ) -> CallToolResult:
        """Force a GUI redraw after Link/shape edits; optionally touch Placement and frame."""
        if touch_objects:
            return tool_fail(
                "refresh_view is visual-only. Use repair_view_placements with an "
                "explicit leased document to touch Placement."
            )
        return refresh_view_operation(
            server_connection(),
            focus_objects=focus_objects,
            focus_object=focus_object,
            touch_objects=touch_objects,
            fit=fit,
            capture=capture,
            view_name=view_name,
            only_text_feedback=server_state().only_text_feedback,
        )

    exports['refresh_view'] = refresh_view
def _register_repair_view_placements(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def repair_view_placements(
        ctx: Context,
        doc_name: str,
        touch_objects: list[str],
        fit: bool = False,
    ) -> CallToolResult:
        """Reassign selected Placement values under the document's active lease."""
        return repair_view_placements_operation(
            server_connection(),
            doc_name=doc_name,
            touch_objects=touch_objects,
            fit=fit,
        )

    exports['repair_view_placements'] = repair_view_placements
def _register_animate_placement(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def animate_placement(
        ctx: Context,
        doc_name: str,
        obj_name: str,
        keyframes: list[dict[str, Any]] | None = None,
        path_object: str | None = None,
        sample_count: int = 12,
        view_name: Literal[
            "Isometric",
            "Front",
            "Top",
            "Right",
            "Back",
            "Left",
            "Bottom",
            "Dimetric",
            "Trimetric",
        ] = "Isometric",
        focus_objects: list[str] | None = None,
        width: int | None = None,
        height: int | None = None,
        encode_video: bool = False,
        fps: float = 8.0,
        output_path: str | None = None,
    ) -> CallToolResult:
        """Animate an object's Placement along keyframes or a path wire, capture frames, restore.

        Prefer this over Shape edits for App::Link visibility. Optionally encodes MP4
        via system ffmpeg when ``encode_video=True``.
        """
        return animate_placement_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_name,
            keyframes=keyframes,
            path_object=path_object,
            sample_count=sample_count,
            view_name=view_name,
            focus_objects=focus_objects,
            width=width,
            height=height,
            encode_video=encode_video,
            fps=fps,
            output_path=output_path,
        )

    exports['animate_placement'] = animate_placement

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register gui_view_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_refresh_view(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_repair_view_placements(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_animate_placement(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
