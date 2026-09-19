"""D-02b: sketch geometry/constraint tools must work on an unauthenticated v1 runtime.

Without an isolated-profile manifest there is no authenticated v2 session. The addon
still registers a typed v1 handler for every sketch tool, but the client returned a
synthetic ``outcome: "uncertain"`` / ``INVALID_RPC_RESPONSE`` without sending anything,
so no sketch could receive geometry or constraints, and the call was misreported as
possibly committed. ``get_runtime_info`` did not list these tools as unavailable either.
"""

from __future__ import annotations

import inspect

import pytest

from freecad_mcp.freecad_client_ops.freecad_connection import FreeCADConnection

pytestmark = pytest.mark.unit

SKETCH_V1_METHODS = (
    "sketch_add_line", "sketch_add_circle", "sketch_add_arc", "sketch_add_rectangle",
    "sketch_add_ellipse", "sketch_add_arc_of_ellipse", "sketch_add_slot",
    "sketch_add_polyline", "sketch_add_bspline", "sketch_add_bspline_through_points",
    "sketch_add_bezier", "sketch_add_regular_polygon", "sketch_add_parametric_curve",
    "sketch_import_points", "sketch_toggle_construction", "sketch_constrain_coincident",
    "sketch_constrain_horizontal", "sketch_constrain_vertical", "sketch_constrain_distance",
    "sketch_constrain_radius", "sketch_constrain_equal", "sketch_constrain_parallel",
    "sketch_constrain_perpendicular", "sketch_constrain_tangent", "sketch_trim",
    "sketch_extend", "sketch_split", "sketch_fillet", "sketch_offset", "sketch_symmetry",
)


def _v1_only_connection(calls: list[tuple[str, tuple[object, ...]]]) -> FreeCADConnection:
    conn = object.__new__(FreeCADConnection)

    def no_v2_session(*_args: object, **_kwargs: object) -> None:
        return None

    def invoke_rpc(method: str, *args: object, **_kwargs: object) -> dict[str, object]:
        calls.append((method, args))
        return {"success": True, "committed": True, "method": method}

    conn._invoke_mutation_v2 = no_v2_session  # type: ignore[method-assign]
    conn.invoke_rpc = invoke_rpc  # type: ignore[method-assign]
    return conn


@pytest.mark.parametrize("method", SKETCH_V1_METHODS)
def test_sketch_tool_falls_back_to_v1_rpc(method: str) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []
    conn = _v1_only_connection(calls)
    bound = getattr(conn, method)
    params = list(inspect.signature(bound).parameters.values())
    args = [f"arg{index}" for index, _param in enumerate(params)]

    result = bound(*args)

    assert result == {"success": True, "committed": True, "method": method}
    assert calls == [(method, tuple(args))]


def test_no_sketch_tool_fabricates_an_uncertain_outcome() -> None:
    source = inspect.getsource(FreeCADConnection)
    assert "typed RPC v2 context is unavailable" not in source
