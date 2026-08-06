# ruff: noqa: E501
"""MCP tool registration — advanced b2 (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    restore_operation,
    run_fem_analysis_operation,
    snapshot_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_snapshot(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def snapshot(ctx: Context, doc_name: str) -> CallToolResult:
        """Snapshot the current document into a ring buffer of the last 5 states (I7).

        Cheap, in-process document copy so a risky step can be undone with one
        ``restore`` call. Returns JSON ``{ok, snapshot_id, doc, count}``.

        Args:
            doc_name: The document to snapshot.
        """
        return snapshot_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
        )

    exports['snapshot'] = snapshot
def _register_restore(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def restore(
        ctx: Context, doc_name: str, snapshot_id: str | None = None
    ) -> CallToolResult:
        """Restore a snapshot, replacing the current document in place (I7).

        If ``snapshot_id`` is omitted, the most recent snapshot is restored. The
        current document is closed and the snapshot file is reopened, so the
        document is restored in place. Returns JSON
        ``{ok, restored_id, doc, new_doc, count}``.

        Args:
            doc_name: The document to restore into (replaced in place).
            snapshot_id: Optional snapshot id returned by ``snapshot``; latest if omitted.
        """
        return restore_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            snapshot_id,
        )

    exports['restore'] = restore
def _register_run_fem_analysis(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def run_fem_analysis(
        ctx: Context,
        doc_name: str,
        analysis_name: str,
        timeout: int = 600,
    ) -> CallToolResult:
        """Run the CalculiX solver on an existing Fem::FemAnalysis container and return summary results.

        Prerequisites in the document:
        - A Part-derived solid (e.g. Part::Box, PartDesign::Body) acting as the geometry.
        - A Fem::AnalysisPython container created via `create_object`.
        - A Fem::MaterialCommon assigned to the geometry, added to the analysis.
        - A Fem::FemMeshGmsh referencing the geometry, added to the analysis (the
          mesh is generated automatically when created via `create_object`).
        - At least one Fem::ConstraintFixed and one Fem::ConstraintForce (or
          ConstraintPressure) bound to faces of the geometry, added to the analysis.

        A SolverCcxTools is auto-created if the analysis has none.

        The solver runs synchronously on the FreeCAD GUI thread and blocks all
        other RPC calls for its duration; do not fan out parallel requests.

        Returns max von Mises stress (MPa), max/min displacement (mm), node count,
        and the working directory CalculiX wrote to. On failure, returns the
        prerequisite-check or solver error along with the working directory for
        triage.

        Args:
            doc_name: Name of the FreeCAD document.
            analysis_name: Name of the Fem::AnalysisPython object.
            timeout: Seconds to wait for the solver (default 600).
        """
        return run_fem_analysis_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            analysis_name,
            timeout,
        )

    exports['run_fem_analysis'] = run_fem_analysis

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register advanced_b2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_snapshot(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_restore(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_run_fem_analysis(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
