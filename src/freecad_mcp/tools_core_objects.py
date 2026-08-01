"""MCP tool registration — core objects (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    delete_object_operation,
    edit_object_operation,
    inspect_references_operation,
    repair_references_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_edit_object(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def edit_object(
        ctx: Context, doc_name: str, obj_name: str, obj_properties: dict[str, Any]
    ) -> CallToolResult:
        """Edit an object in FreeCAD.
        This tool is used when the `create_object` tool cannot handle the object creation.

        Args:
            doc_name: The name of the document to edit the object in.
            obj_name: The name of the object to edit.
            obj_properties: The properties of the object to edit. Placement-typed
                properties such as ``Placement`` and ``AttachmentOffset`` accept the
                same dict form returned by ``get_object``. ``Rotation.Angle`` is in
                **degrees** (FreeCAD's Python ``Rotation.Angle`` property is radians;
                MCP converts on serialize/deserialize so get→edit round-trips)::

                    {"Base": {"x": 0, "y": 0, "z": 10},
                     "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90}}

        Returns:
            A message indicating the success or failure of the object editing and a
            screenshot of the object.
        """
        return edit_object_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_name,
            obj_properties,
        )

    exports['edit_object'] = edit_object
def _register_inspect_references(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def inspect_references(
        ctx: Context,
        doc_name: str,
        object_names: list[str] | None = None,
        only_invalid: bool = False,
        validate: bool = False,
    ) -> CallToolResult:
        """Inspect link/subelement properties without evaluating their owner shapes.

        This is the recovery-safe alternative to ``get_object`` for a document that
        contains stale ``EdgeNNN``, ``FaceNNN``, or ``VertexNNN`` references. It
        scans link properties such as ``Support``, ``AttachmentSupport``, and a
        sketch's ordered ``ExternalGeometry`` list. It never recomputes the document.

        Args:
            doc_name: Open FreeCAD document name.
            object_names: Optional owner objects to inspect; omit to scan the document.
            only_invalid: Return only properties containing invalid subelements.
            validate: Resolve referenced subelements on their target shapes. Leave
                false for circularly broken documents; validity is then reported as
                unevaluated instead of reading ``Shape``.

        Returns:
            Structured link properties, preserving target and subelement order.
        """
        return inspect_references_operation(
            server_connection(),
            doc_name,
            object_names,
            only_invalid=only_invalid,
            validate=validate,
        )

    exports['inspect_references'] = inspect_references
def _register_repair_references(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def repair_references(
        ctx: Context,
        doc_name: str,
        repairs: list[dict[str, Any]],
        recompute: bool = False,
        validate: bool = False,
    ) -> CallToolResult:
        """Atomically replace broken link/subelement properties without recomputing.

        Use this when stale external geometry prevents normal MCP write/evaluate
        calls. Each repair replaces one complete link property. Keeping the same
        reference-list order preserves Sketcher external-geometry indices.

        Example ``repairs`` value::

            [{
              "object": "ServoEdgeBinder",
              "property": "Support",
              "references": [{
                "document": "Model",
                "object": "ServoBody",
                "subelements": ["Edge42"]
              }]
            }]

        Batch every known broken property into one call. The batch is preflighted
        and applied in a FreeCAD transaction. Recompute defaults to false so all
        circularly broken links can be repaired before dependent geometry evaluates.
        This tool does not save the document.

        Args:
            doc_name: Open FreeCAD document containing the owner objects.
            repairs: Complete replacement references for each owner property.
            recompute: Recompute once after committing the entire batch.
            validate: Confirm proposed subelements exist before writing. This reads
                target shapes, so leave false for the circular-recovery path and
                validate with an explicit recompute after the complete batch.

        Returns:
            Applied properties, commit state, deferred/attempted recompute state,
            and any invalid links remaining on the repaired owner objects.
        """
        return repair_references_operation(
            server_connection(),
            doc_name,
            repairs,
            recompute=recompute,
            validate=validate,
        )

    exports['repair_references'] = repair_references
def _register_delete_object(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def delete_object(
        ctx: Context,
        doc_name: str,
        obj_name: str,
        recursive: bool = False,
        force: bool = False,
    ) -> CallToolResult:
        """Delete an object without silently orphaning its dependents (I5 / P6).

        FreeCAD's delete deliberately does not remove an object's dependents, leaving
        them Invalid. To avoid silent orphans this tool:
          * ``recursive=True`` -> remove dependents (leaves first) then the object;
          * ``force=True``      -> remove only the object and report the orphans left;
          * otherwise           -> refuse and list the dependents so the agent decides.

        Args:
            doc_name: The name of the document to delete the object from.
            obj_name: The name of the object to delete.
            recursive: If True, delete the object's dependents first (no orphans).
            force: If True, delete only the object even if it has dependents (orphans
                remain and are reported).

        Returns:
            JSON ``{ok, object, deleted, refused, dependents|orphans_left, ...}``
            plus a recompute log of any non-clean objects, and a screenshot.
        """
        return delete_object_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_name,
            recursive=recursive,
            force=force,
        )

    exports['delete_object'] = delete_object

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register core_objects MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_edit_object(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_inspect_references(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_repair_references(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_delete_object(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
