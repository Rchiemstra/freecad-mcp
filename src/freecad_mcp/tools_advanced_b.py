"""MCP tool registration — advanced b (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    capture_state_operation,
    geometric_diff_operation,
    relink_references_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_relink_references(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def relink_references(
        ctx: Context, doc_name: str, from_obj: str, to_obj: str
    ) -> CallToolResult:
        """Re-point every reference to ``from_obj`` so it points to ``to_obj`` (M5).

        Scans all link-type properties (AttachmentSupport, Support, Profile, Base,
        Tool, Source, Group, ...) of all document objects and re-points them, making
        rebuilds non-destructive. Subshape names are preserved; mismatches surface
        via the recompute log. Returns JSON ``{ok, from, to, relinked, count}``.

        Args:
            doc_name: The document to edit.
            from_obj: The object whose references are being redirected away from.
            to_obj: The object references should now point to.
        """
        return relink_references_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            from_obj,
            to_obj,
        )

    exports['relink_references'] = relink_references
def _register_capture_state(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def capture_state(
        ctx: Context, doc_name: str, object_names: list[str] | None = None
    ) -> CallToolResult:
        """Capture a compact geometric state for a set of objects (I10 / P10).

        Records each object's placement, bounding box and face/edge counts. Pass the
        returned JSON to ``geometric_diff`` to produce a text-only diff when a
        viewable image can't be returned.

        Args:
            doc_name: The document to capture.
            object_names: Optional list of object names; all objects when None.
        """
        return capture_state_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_names,
        )

    exports['capture_state'] = capture_state
def _register_geometric_diff(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def geometric_diff(
        ctx: Context,
        doc_name: str,
        before: dict,
        object_names: list[str] | None = None,
    ) -> CallToolResult:
        """Structured geometric diff between a captured ``before`` state and now (I10).

        The P10 text-only fallback: returns JSON
        ``{ok, doc, diffs: [{name, bbox_before/after, placement_before/after,
        faces_added/removed, changed}]}`` when a viewable image can't be returned.

        Args:
            doc_name: The document to diff against.
            before: A state dict previously returned by ``capture_state``.
            object_names: Optional list of object names; all objects when None.
        """
        return geometric_diff_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            before,
            object_names,
        )

    exports['geometric_diff'] = geometric_diff

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register advanced_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_relink_references(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_capture_state(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_geometric_diff(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
