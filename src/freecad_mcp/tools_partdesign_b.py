"""MCP tool registration — partdesign b (Phase 7 / 7D)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    face_normal_operation,
    find_edges_operation,
    find_faces_operation,
    preview_attachment_operation,
)
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .freecad_client import FreeCADConnection
    from .instrumented_server import InstrumentedFastMCP
    from .lease_manager import StaleLeaseRecoveryOrchestrator
    from .server_state import ServerState
def _register_preview_attachment(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def preview_attachment(ctx: Context, doc_name: str, datum_name: str) -> CallToolResult:
        """Preview an existing datum's attachment — a read-only P1 diagnostic.

        Reports the support reference, the support face/edge global centre and
        normal, the datum's global base/normal, the owning bodies and their
        placements, ``source_body_placement_dropped`` (True when the support lives
        in a different body with a non-identity placement — the cross-body
        attachment drop risk), and a signed distance + normal-angle diff between the
        datum and its support.

        Use this BEFORE building geometry on a cross-body datum, and to debug a
        datum that landed in the wrong place, instead of rebuilding the model.

        Args:
            doc_name: The document containing the datum.
            datum_name: The name of the datum (PartDesign::Plane/Line/Point, or any
                object with an AttachmentSupport) to inspect.
        """
        return preview_attachment_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            datum_name,
        )

    exports['preview_attachment'] = preview_attachment
def _register_find_faces(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def find_faces(
        ctx: Context,
        doc_name: str,
        object_name: str,
        type: str | None = None,
        normal_approx: dict | list | None = None,
        center_approx: dict | list | None = None,
        radius: float | None = None,
        tol: float = 1e-3,
        center_tol: float = 1.0,
        limit: int = 10,
    ) -> CallToolResult:
        """Find faces of an object by geometry — removes face-index fragility (I4).

        Returns a ranked JSON list of faces matching the criteria, each with its
        global centre, global normal, area and radius. Ask for "the top planar face"
        (``type='Plane', normal_approx={'x':0,'y':0,'z':1}``) instead of guessing
        ``Face6``.

        Args:
            doc_name: The document containing the object.
            object_name: The object whose faces to search.
            type: Optional surface type filter: 'Plane', 'Cylinder', 'Cone',
                'Sphere', 'Toroid'.
            normal_approx: Optional {'x','y','z'} (or [x,y,z]) vector; faces whose
                normal is parallel to this within ``tol`` are kept.
            center_approx: Optional point; faces whose global centre is within
                ``center_tol`` mm of it are kept, and results are ranked by closeness.
            radius: Optional radius; cylindrical/spherical faces within ``tol`` are kept.
            tol: Parallelism and radius tolerance (default 1e-3).
            center_tol: Centre proximity tolerance in mm (default 1.0).
            limit: Maximum number of results (default 10).
        """
        return find_faces_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            type=type,
            normal_approx=normal_approx,
            center_approx=center_approx,
            radius=radius,
            tol=tol,
            center_tol=center_tol,
            limit=limit,
        )

    exports['find_faces'] = find_faces
def _register_find_edges(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def find_edges(
        ctx: Context,
        doc_name: str,
        object_name: str,
        type: str | None = None,
        direction_approx: dict | list | None = None,
        center_approx: dict | list | None = None,
        radius: float | None = None,
        tol: float = 1e-3,
        center_tol: float = 1.0,
        limit: int = 10,
    ) -> CallToolResult:
        """Find edges of an object by geometry — removes edge-index fragility (I4).

        Returns a ranked JSON list of edges matching the criteria, each with its
        global centre, global direction, length and radius. E.g. find the circular
        edge of radius 5 on top of a cylinder with
        ``type='Circle', radius=5, center_approx={'x':0,'y':0,'z':10}``.

        Args:
            doc_name: The document containing the object.
            object_name: The object whose edges to search.
            type: Optional curve type filter: 'Line', 'Circle', 'Ellipse',
                'BSplineCurve'.
            direction_approx: Optional vector; edges whose axis is parallel to this
                within ``tol`` are kept (use for line edges).
            center_approx: Optional point; edges whose global centre is within
                ``center_tol`` mm are kept, results ranked by closeness.
            radius: Optional radius; circular/elliptical edges within ``tol`` are kept.
            tol: Parallelism and radius tolerance (default 1e-3).
            center_tol: Centre proximity tolerance in mm (default 1.0).
            limit: Maximum number of results (default 10).
        """
        return find_edges_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            type=type,
            direction_approx=direction_approx,
            center_approx=center_approx,
            radius=radius,
            tol=tol,
            center_tol=center_tol,
            limit=limit,
        )

    exports['find_edges'] = find_edges
def _register_face_normal(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def face_normal(
        ctx: Context, doc_name: str, object_name: str, face: str
    ) -> CallToolResult:
        """Return the global normal (and centre) of a face (M6 / P8 guard).

        Derives the vector from the face geometry via ``normalAt`` rotated by the
        object's global placement, avoiding the Direction-vs-Axis trap. Returns JSON
        ``{ok, object, subshape, type, global_center, global_normal, radius}``.

        Args:
            doc_name: The document containing the object.
            object_name: The object whose face to inspect.
            face: The face name, e.g. ``"Face3"``.
        """
        return face_normal_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            object_name,
            face,
        )

    exports['face_normal'] = face_normal

def register(
    mcp: InstrumentedFastMCP,
    *,
    state: ServerState,
    get_freecad_connection: Callable[[], FreeCADConnection],
    stale_recovery: StaleLeaseRecoveryOrchestrator,
) -> dict[str, object]:
    """Register partdesign_b MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_preview_attachment(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_find_faces(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_find_edges(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    _register_face_normal(
        mcp,
        state=state,
        get_freecad_connection=get_freecad_connection,
        stale_recovery=stale_recovery,
        exports=exports,
    )
    return exports
