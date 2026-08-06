"""MCP tool registration — gear 2 (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    check_gear_pair_operation,
    compute_gear_geometry_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_compute_gear_geometry(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def compute_gear_geometry(
        ctx: Context,
        teeth: int,
        module: float,
        pressure_angle: float = 20.0,
        clearance: float = 0.0,
        backlash: float = 0.0,
        helix_angle: float = 0.0,
    ) -> CallToolResult:
        """Compute standard gear geometry parameters without creating geometry.

        Returns pitch diameter, base diameter, addendum, dedendum, circular pitch,
        and base pitch for the specified gear.

        Args:
            teeth: Number of teeth.
            module: Gear module in mm.
            pressure_angle: Pressure angle in degrees (default 20).
            clearance: Extra root clearance in mm.
            backlash: Tooth backlash in mm.
            helix_angle: Helix angle in degrees (0 = spur gear).

        Returns:
            JSON with all standard gear parameters.
        """
        return compute_gear_geometry_operation(
            server_connection(),
            server_state().only_text_feedback,
            teeth,
            module,
            pressure_angle,
            clearance,
            backlash,
            helix_angle,
        )

    exports['compute_gear_geometry'] = compute_gear_geometry
def _register_check_gear_pair(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def check_gear_pair(
        ctx: Context,
        teeth1: int,
        module1: float,
        teeth2: int,
        module2: float,
        pressure_angle: float = 20.0,
        center_distance: float | None = None,
    ) -> CallToolResult:
        """Verify that two gears form a valid meshing pair.

        Checks module compatibility, computes gear ratio and theoretical centre
        distance. Optionally validates a specified centre distance.

        Args:
            teeth1: Teeth count of the first gear (driver).
            module1: Module of the first gear in mm.
            teeth2: Teeth count of the second gear (driven).
            module2: Module of the second gear in mm.
            pressure_angle: Shared pressure angle in degrees.
            center_distance: Optional measured centre distance to validate in mm.

        Returns:
            JSON with ``meshes`` (bool), ``gear_ratio``, ``theoretical_cd_mm``, and notes.
        """
        return check_gear_pair_operation(
            server_connection(),
            server_state().only_text_feedback,
            teeth1,
            module1,
            teeth2,
            module2,
            pressure_angle,
            center_distance,
        )

    exports['check_gear_pair'] = check_gear_pair

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register gear_2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_compute_gear_geometry(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_check_gear_pair(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
