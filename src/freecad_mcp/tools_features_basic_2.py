"""MCP tool registration — features basic 2 (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    mirror_feature_operation,
    polar_pattern_feature_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_polar_pattern_feature(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def polar_pattern_feature(
        ctx: Context,
        doc_name: str,
        feature_name: str,
        pattern_name: str,
        occurrences: int,
        angle: float = 360.0,
        axis: str = "Z_Axis",
        body_name: str | None = None,
        reversed_dir: bool = False,
    ) -> CallToolResult:
        """Repeat an existing PartDesign feature around an axis.

        Use this for circular hole patterns or radial repeats of sketch-based Pads
        and Pockets. The source feature must be inside a PartDesign Body.

        Args:
            doc_name: The document containing the body and source feature.
            feature_name: Existing feature to repeat, for example `Pocket` or `Pad`.
            pattern_name: Name for the resulting PolarPattern feature.
            occurrences: Number of repeated instances, including the original.
            angle: Total angular span in degrees. Defaults to 360.
            axis: Axis or reference edge. Examples: `Z_Axis`, `X_Axis`, or
                `ObjectName:Edge1`.
            body_name: Optional explicit PartDesign Body name.
            reversed_dir: If true, reverse the angular direction.

        Returns:
            A message indicating success or failure and an isometric screenshot.

        Examples:
            Pattern a pocket 6 times around the Z axis:
            ```json
            {"doc_name": "Part", "feature_name": "Pocket", "pattern_name": "BoltCircle",
             "occurrences": 6}
            ```
        """
        return polar_pattern_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            feature_name,
            pattern_name,
            occurrences,
            angle,
            axis,
            body_name,
            reversed_dir,
        )

    exports['polar_pattern_feature'] = polar_pattern_feature
def _register_mirror_feature(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def mirror_feature(
        ctx: Context,
        doc_name: str,
        feature_name: str,
        mirror_name: str,
        plane: str = "YZ_Plane",
        body_name: str | None = None,
    ) -> CallToolResult:
        """Mirror an existing PartDesign feature across a plane.

        Use this after creating a sketch-based feature such as a Pad or Pocket.
        The source feature must be inside a PartDesign Body.

        Args:
            doc_name: The document containing the body and source feature.
            feature_name: Existing feature to mirror, for example `Pocket` or `Pad`.
            mirror_name: Name for the resulting Mirrored feature.
            plane: Mirror plane. Examples: `YZ_Plane`, `XZ_Plane`, `XY_Plane`,
                or `ObjectName:Face1`.
            body_name: Optional explicit PartDesign Body name.

        Returns:
            A message indicating success or failure and an isometric screenshot.

        Examples:
            Mirror a pocket across the YZ plane:
            ```json
            {"doc_name": "Part", "feature_name": "Pocket", "mirror_name": "PocketMirror",
             "plane": "YZ_Plane"}
            ```
        """
        return mirror_feature_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            feature_name,
            mirror_name,
            plane,
            body_name,
        )

    exports['mirror_feature'] = mirror_feature

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register features_basic_2 MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_polar_pattern_feature(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_mirror_feature(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
