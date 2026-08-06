"""MCP tool registration — partdesign a (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    create_datum_plane_operation,
    create_part_container_operation,
    create_subshape_binder_operation,
    move_object_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_create_part_container(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_part_container(
        ctx: Context,
        doc_name: str,
        part_name: str,
        parent_container: str | None = None,
        if_exists: Literal["error", "skip", "replace"] = "error",
    ) -> CallToolResult:
        """Create an App::Part assembly container."""
        return create_part_container_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            part_name,
            parent_container,
            if_exists,
        )

    exports['create_part_container'] = create_part_container
def _register_move_object(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def move_object(
        ctx: Context,
        doc_name: str,
        obj_name: str,
        target_container: str,
        remove_from_old_parent: bool = True,
    ) -> CallToolResult:
        """Move an object into a PartDesign Body or App::Part container."""
        return move_object_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_name,
            target_container,
            remove_from_old_parent,
        )

    exports['move_object'] = move_object
def _register_create_subshape_binder(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_subshape_binder(
        ctx: Context,
        doc_name: str,
        binder_name: str,
        source_object: str,
        sub_elements: list[str] | None = None,
        target_body: str | None = None,
        target_container: str | None = None,
        relative: bool = False,
        sync_placement: bool = True,
        if_exists: Literal["error", "skip", "replace"] = "error",
    ) -> CallToolResult:
        """Create a PartDesign SubShapeBinder with placement validation."""
        return create_subshape_binder_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            binder_name,
            source_object,
            sub_elements,
            target_body,
            target_container,
            relative,
            sync_placement,
            if_exists,
        )

    exports['create_subshape_binder'] = create_subshape_binder
def _register_create_datum_plane(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_datum_plane(
        ctx: Context,
        doc_name: str,
        plane_name: str,
        body_name: str,
        mode: Literal[
            "midpoint_between_faces",
            "through_point",
            "offset_from_face",
            "between_parallel_planes",
            "plane_from_binder_face",
        ],
        source_ref: str | None = None,
        face_a: str | None = None,
        face_b: str | None = None,
        offset_along_normal: list[float] | None = None,
        map_mode: str = "FlatFace",
        if_exists: Literal["error", "skip", "replace"] = "error",
    ) -> CallToolResult:
        """Create a PartDesign datum plane for assembly reference workflows.

        Recipes (avoid the silent P1/P3 traps):
          * **XY_Plane + AttachmentOffset instead of a rotated datum.** Prefer
            attaching to an origin ``XY_Plane``/``XZ_Plane``/``YZ_Plane`` and using
            ``offset_along_normal`` + ``AttachmentOffset`` to position the plane,
            rather than creating a datum on a default axis and then rotating its
            Placement. A rotated ``Deactivated`` datum can drop the rotation (P3).
          * **Identity-body rebuild for cross-body datums.** When a datum in Body A
            must reference a face in Body B, keep Body B at an identity placement
            (move the geometry into Body B via a pad/transform instead of moving the
            body). FreeCAD's attacher can drop a non-identity source-body placement
            (P1). Use ``preview_attachment`` to confirm, and ``placement_audit`` to
            find risk concentrations.
        """
        return create_datum_plane_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            plane_name,
            body_name,
            mode,
            source_ref,
            face_a,
            face_b,
            offset_along_normal,
            map_mode,
            if_exists,
        )

    exports['create_datum_plane'] = create_datum_plane

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register partdesign_a MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_create_part_container(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_move_object(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_create_subshape_binder(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_create_datum_plane(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
