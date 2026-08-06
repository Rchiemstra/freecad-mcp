"""MCP tool registration — core execute (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    execute_code_async_operation,
    execute_code_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_execute_code_async(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def execute_code_async(ctx: Context, code: str) -> CallToolResult:
        """Deprecated legacy background execution; blocked in lease enforcement.

        This compatibility tool is unavailable in ``enforce`` mode because it has
        no explicit document scope or GUI-thread lease revalidation. Use snapshot
        worker analysis for read-only work and typed leased mutations to apply a
        result. In off/observe compatibility mode, use this ONLY for long-running
        background computations that do NOT touch the
        FreeCAD GUI or mutate the FreeCAD document tree directly.

        This tool runs the submitted code in a background thread and returns
        immediately. Because it does not run on FreeCAD's main GUI thread, the code
        must NOT call FreeCADGui APIs, manipulate the active view or selection, create
        or edit document objects, change object properties, call doc.recompute(), or
        save documents.

        For code that touches FreeCAD documents, document objects, FreeCADGui, the
        active view, selection, or document objects, use typed RPC tools. Public
        ``execute_code(read_only=True)`` runs only in an isolated snapshot worker;
        live mutating execution is a separately enabled compatibility path and is
        disabled by default in lease enforcement mode.

        Use execute_code_async only for background-safe work such as long-running
        pure OCCT geometry calculations (e.g. fuse/cut/loft on already-fetched shapes)
        or other CPU-bound computations that do not interact with the document or GUI.

        Typical usage pattern:
        1. Fetch shapes into local variables first (via execute_code on the GUI thread).
        2. Store intermediate results in a module-level Python variable (not in the
           FreeCAD document) so execute_code can read them later.
        3. Run the heavy computation via execute_code_async.
        4. After the expected computation time has elapsed, apply results to the
           document via execute_code (which runs on the GUI thread).

        Args:
            code: Background-safe Python code to execute.

        Returns:
            A message confirming that background execution has started.
        """
        return execute_code_async_operation(server_connection(), code)

    exports['execute_code_async'] = execute_code_async
def _register_execute_code(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def execute_code(
        ctx: Context,
        code: str,
        document: str | None = None,
        recompute: str = "none",
        recompute_documents: list[str] | None = None,
        affected_documents: list[str] | None = None,
        read_only: bool = False,
        restore_active_document: bool = True,
        activate_document: bool = False,
        capture_view: bool = False,
        execution_mode: Literal["gui", "worker", "auto"] = "auto",
        timeout_seconds: float | None = None,
        link_policy: Literal["strict", "warn"] = "strict",
        allow_gui_geometry_loop: bool = False,
    ) -> CallToolResult:
        """Execute arbitrary Python code in FreeCAD.

        CHOOSING A MODE — expensive geometry loops must not run on the GUI thread.
        Any iteration (for/while/comprehension) containing an expensive OCCT call
        (``distToShape``/``isInside``/``common``/``cut``/``fuse``/``section``/
        ``removeSplitter``/``isValid``/``check``) MUST use ``read_only=true`` +
        ``execution_mode="worker"``
        + ``timeout_seconds``. Such loops are non-interruptible on the GUI thread and
        will freeze FreeCAD (a timeout cannot stop them). They are blocked in ``gui``
        mode unless you pass ``allow_gui_geometry_loop=true``, which is reserved for a
        genuine, bounded live-document mutation that cannot run against a worker
        snapshot. ``isInside`` sampling loops are worker-only and cannot use that
        override. Split large sweeps into small batches, and after a GUI timeout do not
        resubmit GUI work until a liveness check (e.g. ``get_worker_status``) passes.
        ``read_only=true`` may temporarily rotate/recompute geometry in the worker
        snapshot; it only forbids modifying the live GUI documents.

        Args:
            code: The Python code to execute.
            document: Target document name for scoped recompute/error reporting.
            recompute: ``none`` (default for inspection), ``target``, or ``all``.
            recompute_documents: Explicit document list to recompute when recompute is ``target``.
            affected_documents: Complete declared write scope for mutating code.
            read_only: Run only against an immutable FreeCADCmd snapshot. This never
                executes arbitrary code against a live GUI document in any lease mode.
            restore_active_document: Restore the active document after execution.
            activate_document: Activate ``document`` before running code.
            capture_view: Include a viewport screenshot (default false).
            execution_mode: Conservative ``auto`` (default), explicit ``gui``, or
                isolated ``worker``. ``read_only=True`` always selects the worker,
                even if ``gui`` is requested.
            timeout_seconds: Hard worker timeout from 1 to 900 seconds.
            link_policy: Worker snapshot policy for broken joint/link refs. ``strict``
                fails the snapshot; ``warn`` continues and returns ``link_warnings``.
                Only meaningful with ``execution_mode="worker"``.
            allow_gui_geometry_loop: Last-resort opt-in to run an expensive-geometry
                loop on the GUI thread (``execution_mode="gui"``, ``read_only=false``)
                for a genuine, bounded live-document mutation. Default false; prefer
                read-only worker mode for any analysis.

        Returns:
            Execution output with structured session/recompute metadata, or an error with traceback.
        """
        return execute_code_operation(
            server_connection(),
            server_state().only_text_feedback,
            code,
            document=document,
            recompute=recompute,
            recompute_documents=recompute_documents,
            affected_documents=affected_documents,
            read_only=read_only,
            restore_active_document=restore_active_document,
            activate_document=activate_document,
            capture_view=capture_view,
            execution_mode=execution_mode,
            timeout_seconds=timeout_seconds,
            link_policy=link_policy,
            allow_gui_geometry_loop=allow_gui_geometry_loop,
        )

    exports['execute_code'] = execute_code

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register core_execute MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_execute_code_async(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_execute_code(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
