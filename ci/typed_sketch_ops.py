"""Metadata for G-sketch-execute-code typed RPC operations."""

from __future__ import annotations

from typing import Literal, TypedDict

SuccessKind = Literal[
    "geometry_index",
    "geometry_indices",
    "constraint_index",
    "geometry_index_samples",
    "sketch_only",
]


class SketchOpSpec(TypedDict):
    name: str
    pascal: str
    upper: str
    success_kind: SuccessKind
    register_module: str
    register_function: str
    operation_name: str
    rpc_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    needs_part: bool
    needs_sketcher: bool
    needs_math: bool


def _pascal(name: str) -> str:
    return "".join(part.title() for part in name.split("_"))


def _spec(
    name: str,
    *,
    success_kind: SuccessKind,
    register_module: str,
    operation_name: str,
    rpc_params: tuple[str, ...],
    optional_params: tuple[str, ...] = (),
    needs_part: bool = True,
    needs_sketcher: bool = False,
    needs_math: bool = False,
) -> SketchOpSpec:
    return {
        "name": name,
        "pascal": _pascal(name),
        "upper": name.upper(),
        "success_kind": success_kind,
        "register_module": register_module,
        "register_function": f"_register_{name}",
        "operation_name": operation_name,
        "rpc_params": rpc_params,
        "optional_params": optional_params,
        "needs_part": needs_part,
        "needs_sketcher": needs_sketcher,
        "needs_math": needs_math,
    }


SKETCH_OPS: tuple[SketchOpSpec, ...] = (
    _spec(
        "sketch_add_line",
        success_kind="geometry_index",
        register_module="tools_sketch_primitives",
        operation_name="Add sketch line",
        rpc_params=("doc_name", "sketch_name", "x1", "y1", "x2", "y2"),
        optional_params=("construction",),
    ),
    _spec(
        "sketch_add_circle",
        success_kind="geometry_index",
        register_module="tools_sketch_primitives",
        operation_name="Add sketch circle",
        rpc_params=("doc_name", "sketch_name", "cx", "cy", "radius"),
        optional_params=("construction",),
    ),
    _spec(
        "sketch_add_arc",
        success_kind="geometry_index",
        register_module="tools_sketch_primitives",
        operation_name="Add sketch arc",
        rpc_params=("doc_name", "sketch_name", "cx", "cy", "radius", "start_angle", "end_angle"),
        optional_params=("construction",),
        needs_math=True,
    ),
    _spec(
        "sketch_add_rectangle",
        success_kind="geometry_indices",
        register_module="tools_sketch_primitives",
        operation_name="Add sketch rectangle",
        rpc_params=("doc_name", "sketch_name", "x1", "y1", "x2", "y2"),
        optional_params=("construction",),
    ),
    _spec(
        "sketch_add_ellipse",
        success_kind="geometry_index",
        register_module="tools_sketch_curves_a2",
        operation_name="Add sketch ellipse",
        rpc_params=("doc_name", "sketch_name", "cx", "cy", "major_radius", "minor_radius"),
        optional_params=("angle", "construction"),
        needs_math=True,
    ),
    _spec(
        "sketch_add_arc_of_ellipse",
        success_kind="geometry_index",
        register_module="tools_sketch_curves_a2",
        operation_name="Add sketch arc of ellipse",
        rpc_params=(
            "doc_name",
            "sketch_name",
            "cx",
            "cy",
            "major_radius",
            "minor_radius",
            "start_angle",
            "end_angle",
        ),
        optional_params=("angle", "construction"),
        needs_math=True,
    ),
    _spec(
        "sketch_add_slot",
        success_kind="geometry_indices",
        register_module="tools_sketch_curves_a2",
        operation_name="Add sketch slot",
        rpc_params=("doc_name", "sketch_name", "x1", "y1", "x2", "y2", "width"),
        optional_params=("construction",),
        needs_math=True,
    ),
    _spec(
        "sketch_add_polyline",
        success_kind="geometry_indices",
        register_module="tools_sketch_curves_a",
        operation_name="Add sketch polyline",
        rpc_params=("doc_name", "sketch_name", "points"),
        optional_params=("closed", "construction"),
    ),
    _spec(
        "sketch_add_bspline",
        success_kind="geometry_index",
        register_module="tools_sketch_curves_a",
        operation_name="Add sketch BSpline",
        rpc_params=("doc_name", "sketch_name", "poles"),
        optional_params=("degree", "weights", "knots", "multiplicities", "periodic", "construction"),
    ),
    _spec(
        "sketch_add_bspline_through_points",
        success_kind="geometry_index",
        register_module="tools_sketch_curves_a",
        operation_name="Add interpolating sketch BSpline",
        rpc_params=("doc_name", "sketch_name", "points"),
        optional_params=("degree", "periodic", "construction"),
    ),
    _spec(
        "sketch_add_bezier",
        success_kind="geometry_index",
        register_module="tools_sketch_curves_a",
        operation_name="Add sketch Bezier",
        rpc_params=("doc_name", "sketch_name", "poles"),
        optional_params=("construction",),
    ),
    _spec(
        "sketch_add_regular_polygon",
        success_kind="geometry_indices",
        register_module="tools_sketch_curves_b",
        operation_name="Add sketch regular polygon",
        rpc_params=("doc_name", "sketch_name", "cx", "cy", "radius", "sides"),
        optional_params=("angle", "construction"),
        needs_math=True,
    ),
    _spec(
        "sketch_add_parametric_curve",
        success_kind="geometry_index_samples",
        register_module="tools_sketch_curves_b",
        operation_name="Add sketch parametric curve",
        rpc_params=("doc_name", "sketch_name", "x_expr", "y_expr", "t_start", "t_end"),
        optional_params=("samples", "construction"),
        needs_math=True,
    ),
    _spec(
        "sketch_import_points",
        success_kind="geometry_indices",
        register_module="tools_sketch_curves_b",
        operation_name="Import sketch points",
        rpc_params=("doc_name", "sketch_name", "points"),
        optional_params=("construction",),
    ),
    _spec(
        "sketch_toggle_construction",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b",
        operation_name="Toggle sketch construction",
        rpc_params=("doc_name", "sketch_name", "geo_indices"),
        optional_params=("construction",),
        needs_part=False,
    ),
    _spec(
        "sketch_constrain_coincident",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_1",
        operation_name="Add coincident constraint",
        rpc_params=("doc_name", "sketch_name", "geo1", "pos1", "geo2", "pos2"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_horizontal",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_1",
        operation_name="Add horizontal constraint",
        rpc_params=("doc_name", "sketch_name", "geo"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_vertical",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_1",
        operation_name="Add vertical constraint",
        rpc_params=("doc_name", "sketch_name", "geo"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_distance",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_1",
        operation_name="Add distance constraint",
        rpc_params=("doc_name", "sketch_name", "geo", "value"),
        optional_params=("pos", "name"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_radius",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_1",
        operation_name="Add radius constraint",
        rpc_params=("doc_name", "sketch_name", "geo", "value"),
        optional_params=("name",),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_equal",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_2",
        operation_name="Add equal constraint",
        rpc_params=("doc_name", "sketch_name", "geo1", "geo2"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_parallel",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_2",
        operation_name="Add parallel constraint",
        rpc_params=("doc_name", "sketch_name", "geo1", "geo2"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_perpendicular",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_2",
        operation_name="Add perpendicular constraint",
        rpc_params=("doc_name", "sketch_name", "geo1", "geo2"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_constrain_tangent",
        success_kind="constraint_index",
        register_module="tools_sketch_constraints_2",
        operation_name="Add tangent constraint",
        rpc_params=("doc_name", "sketch_name", "geo1", "geo2"),
        needs_part=False,
        needs_sketcher=True,
    ),
    _spec(
        "sketch_trim",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b2",
        operation_name="Trim sketch geometry",
        rpc_params=("doc_name", "sketch_name", "geo_index", "point_x", "point_y"),
    ),
    _spec(
        "sketch_extend",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b2",
        operation_name="Extend sketch geometry",
        rpc_params=("doc_name", "sketch_name", "geo_index", "increment"),
        optional_params=("end_point",),
        needs_part=False,
    ),
    _spec(
        "sketch_split",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b2",
        operation_name="Split sketch geometry",
        rpc_params=("doc_name", "sketch_name", "geo_index", "point_x", "point_y"),
    ),
    _spec(
        "sketch_fillet",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b2",
        operation_name="Fillet sketch geometry",
        rpc_params=("doc_name", "sketch_name", "geo1", "geo2", "radius"),
    ),
    _spec(
        "sketch_symmetry",
        success_kind="sketch_only",
        register_module="tools_sketch_curves_b2",
        operation_name="Apply sketch symmetry",
        rpc_params=("doc_name", "sketch_name", "geo_indices", "symmetry_geo"),
        optional_params=("copy",),
        needs_part=False,
        needs_sketcher=True,
    ),
)

SKETCH_OP_BY_NAME = {spec["name"]: spec for spec in SKETCH_OPS}

__all__ = ["SKETCH_OPS", "SKETCH_OP_BY_NAME", "SketchOpSpec"]
