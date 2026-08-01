"""MCP tool registration — gui document b (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    activate_document_operation,
    get_gui_state_operation,
    get_selection_operation,
    recompute_and_wait_operation,
    select_subshapes_operation,
    set_section_view_operation,
    set_tree_expanded_operation,
)
from .tools_server_surfaces import server_connection

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_activate_document(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def activate_document(ctx: Context, doc_name: str) -> CallToolResult:
        """Make an already-open document the active GUI document."""
        return activate_document_operation(server_connection(), doc_name)

    exports['activate_document'] = activate_document
def _register_set_tree_expanded(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def set_tree_expanded(
        ctx: Context,
        doc_name: str,
        object_names: list[str] | None = None,
        mode: Literal[
            "expand", "collapse", "expand_document", "collapse_document"
        ] = "expand",
    ) -> CallToolResult:
        """Expand or collapse model-tree items in the FreeCAD GUI.

        Selects ``object_names`` then runs Std_TreeExpand / Std_TreeCollapse.
        Modes ``expand_document`` / ``collapse_document`` operate on the whole tree.
        """
        return set_tree_expanded_operation(
            server_connection(), doc_name, object_names, mode
        )

    exports['set_tree_expanded'] = set_tree_expanded
def _register_select_subshapes(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def select_subshapes(
        ctx: Context,
        doc_name: str,
        selections: list[Any],
        clear: bool = True,
    ) -> CallToolResult:
        """Select GUI-visible objects or sub-shapes (FaceN/EdgeN/VertexN).

        Each selection may be ``\"Box\"``, ``\"Box:Face1\"``, or
        ``{\"object\": \"Box\", \"sub\": \"Face1\"}``. Prefer ``find_faces`` to
        discover indices, then this tool to highlight them in the GUI.
        """
        return select_subshapes_operation(
            server_connection(), doc_name, selections, clear
        )

    exports['select_subshapes'] = select_subshapes
def _register_get_selection(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_selection(ctx: Context) -> CallToolResult:
        """Return the current FreeCADGui selection (document/object/sub)."""
        return get_selection_operation(server_connection())

    exports['get_selection'] = get_selection
def _register_get_gui_state(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_gui_state(ctx: Context) -> CallToolResult:
        """Report the active GUI context (read-only).

        Returns JSON with the active document, active PartDesign Body, active
        workbench, the object currently in edit-mode, and the current selection.
        Use it to orient before editing -- e.g. confirm the right Body is active
        before adding a sketch/feature, or check whether a Sketch is open for edit.
        """
        return get_gui_state_operation(server_connection())

    exports['get_gui_state'] = get_gui_state
def _register_recompute_and_wait(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def recompute_and_wait(ctx: Context, doc_name: str) -> CallToolResult:
        """Recompute a document and block until the GUI is idle, then report state.

        An explicit recompute-complete + GUI-idle barrier: runs the recompute on the
        GUI thread, drains queued Qt events, and returns per-object recompute state
        (errors, still-Touched objects, whether the document settled). Run it after a
        batch of edits, or after an execute_code that may have left async work, before
        trusting follow-up model checks. Complements ``check_rpc_sync`` (which only
        proves the RPC queue is live, not that a recompute finished).
        """
        return recompute_and_wait_operation(server_connection(), doc_name)

    exports['recompute_and_wait'] = recompute_and_wait
def _register_set_section_view(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def set_section_view(
        ctx: Context,
        enabled: bool | None = None,
        base: list[float] | None = None,
        normal: list[float] | None = None,
        placement: dict[str, Any] | None = None,
        no_manip: bool = True,
    ) -> CallToolResult:
        """Enable, disable, or query the active view clipping (section) plane.

        Pass ``enabled=True/False`` to toggle. Optionally set plane ``base`` +
        ``normal`` (or a full ``placement`` dict). Omit args to query status.
        """
        return set_section_view_operation(
            server_connection(),
            enabled=enabled,
            placement=placement,
            base=base,
            normal=normal,
            no_manip=no_manip,
        )

    exports['set_section_view'] = set_section_view

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register gui_document_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_activate_document(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_set_tree_expanded(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_select_subshapes(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_get_selection(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_get_gui_state(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_recompute_and_wait(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_set_section_view(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
