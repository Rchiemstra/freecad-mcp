"""MCP tool registration — parametric body (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    body_create_operation,
    body_set_tip_operation,
    diagnose_parametric_operation,
    get_sketch_diagnostics_operation,
    sketch_attach_operation,
    sketch_edit_constraint_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_body_create(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def body_create(
        ctx: Context,
        doc_name: str,
        body_name: str,
    ) -> CallToolResult:
        """Create a PartDesign::Body.

        Recommended pattern: Body → Sketch on XY_Plane → Pad → Pocket.
        """
        return body_create_operation(
            server_connection(), server_state().only_text_feedback, doc_name, body_name
        )

    exports['body_create'] = body_create
def _register_body_set_tip(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def body_set_tip(
        ctx: Context,
        doc_name: str,
        body_name: str,
        feature_name: str,
    ) -> CallToolResult:
        """Set a Body's Tip to a feature (keeps the PartDesign history tip correct)."""
        return body_set_tip_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            body_name,
            feature_name,
        )

    exports['body_set_tip'] = body_set_tip
def _register_sketch_attach(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_attach(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        support: Any,
        attachment_offset: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Attach a sketch to an origin plane or face support.

        ``support`` may be:
        - ``\"XY_Plane\"`` / ``\"XZ_Plane\"`` / ``\"YZ_Plane\"``
        - ``\"ObjectName:FaceN\"``
        - ``{\"object\": \"Obj\", \"subname\": \"Face1\"}``

        ``attachment_offset`` is optional and uses the same Placement dict form as
        ``edit_object`` / ``get_object``. ``Rotation.Angle`` is in **degrees**.
        Prefer this over rotating ``Placement`` on a deactivated attachment (P3 trap).
        """
        return sketch_attach_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            support,
            attachment_offset,
        )

    exports['sketch_attach'] = sketch_attach
def _register_sketch_edit_constraint(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def sketch_edit_constraint(
        ctx: Context,
        doc_name: str,
        sketch_name: str,
        value: float | None = None,
        name: str | None = None,
        index: int | None = None,
    ) -> CallToolResult:
        """Edit a dimensional constraint by stable ``name`` (preferred) or index.

        After trim/fillet, geo indices shift — always prefer ``name``.
        """
        return sketch_edit_constraint_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            sketch_name,
            value=value,
            name=name,
            index=index,
        )

    exports['sketch_edit_constraint'] = sketch_edit_constraint
def _register_diagnose_parametric(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def diagnose_parametric(
        ctx: Context,
        doc_name: str,
        object_name: str | None = None,
    ) -> CallToolResult:
        """Diagnose parametric / expression / sketch issues.

        Reports invalid objects, expression bind issues, and sketch constraint
        conflict/redundant/malformed summaries. Scope to one object or the whole doc.
        """
        return diagnose_parametric_operation(
            server_connection(), server_state().only_text_feedback, doc_name, object_name
        )

    exports['diagnose_parametric'] = diagnose_parametric
def _register_get_sketch_diagnostics(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def get_sketch_diagnostics(
        ctx: Context, doc_name: str, sketch_name: str
    ) -> CallToolResult:
        """Return solver diagnostics for a Sketcher sketch.

        Call this before pad_feature to verify the sketch is fully constrained and
        closed. Returns degrees of freedom, constraint counts, conflicting /
        redundant constraint indices, solver message, and whether the sketch wire
        is closed.

        Args:
            doc_name: The document containing the sketch.
            sketch_name: Name of the sketch to inspect.

        Returns:
            JSON dict with:
            - geometry_count: number of geometry elements
            - constraint_count: number of constraints
            - state: object state flags (e.g. ['Up-to-date'])
            - conflicting_constraints: list of conflicting constraint indices
            - redundant_constraints: list of redundant constraint indices
            - malformed_constraints: list of malformed constraint indices
            - solver_message: solver status string (if available)
            - is_closed: whether the sketch wire forms a closed profile

        Examples:
            ```json
            {"doc_name": "Part", "sketch_name": "Sketch"}
            ```
        """
        return get_sketch_diagnostics_operation(
            server_connection(), doc_name, sketch_name
        )

    exports['get_sketch_diagnostics'] = get_sketch_diagnostics

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register parametric_body MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_body_create(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_body_set_tip(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_attach(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_sketch_edit_constraint(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_diagnose_parametric(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_get_sketch_diagnostics(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
