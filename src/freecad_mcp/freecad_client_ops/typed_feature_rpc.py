"""JSON-RPC client helpers for typed G-features-p3 mutations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class _TypedFeatureConnection(Protocol):
    server: object

    def _invoke_mutation_v2(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        document_names: tuple[str, ...] = (),
        operation_name: str | None = None,
    ) -> object: ...


def invoke_typed_feature_rpc(
    conn: _TypedFeatureConnection,
    method: str,
    params: Mapping[str, object],
    *,
    document_name: str,
    operation_name: str,
) -> object:
    """Send one named JSON-RPC mutation, falling back to the addon method."""

    routed = conn._invoke_mutation_v2(
        method,
        params,
        document_names=(document_name,),
        operation_name=operation_name,
    )
    if routed is not None:
        return routed
    fallback = getattr(conn.server, method, None)
    if not callable(fallback):
        raise TypeError(f"FreeCAD RPC server has no callable {method}")
    return fallback(**dict(params))


def _call(
    conn: _TypedFeatureConnection,
    method: str,
    params: Mapping[str, object],
    operation_name: str,
) -> object:
    document_name = params["doc_name"]
    name = document_name if isinstance(document_name, str) else str(document_name)
    return invoke_typed_feature_rpc(
        conn,
        method,
        params,
        document_name=name,
        operation_name=operation_name,
    )


def boolean_difference(
    conn: _TypedFeatureConnection,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> object:
    return _call(
        conn,
        "boolean_difference",
        {
            "doc_name": doc_name,
            "shape1": shape1,
            "shape2": shape2,
            "result_name": result_name,
        },
        "Boolean difference",
    )


def boolean_intersection(
    conn: _TypedFeatureConnection,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> object:
    return _call(
        conn,
        "boolean_intersection",
        {
            "doc_name": doc_name,
            "shape1": shape1,
            "shape2": shape2,
            "result_name": result_name,
        },
        "Boolean intersection",
    )


def boolean_union(
    conn: _TypedFeatureConnection,
    doc_name: str,
    shape1: str,
    shape2: str,
    result_name: str,
) -> object:
    return _call(
        conn,
        "boolean_union",
        {
            "doc_name": doc_name,
            "shape1": shape1,
            "shape2": shape2,
            "result_name": result_name,
        },
        "Boolean union",
    )


def chamfer_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    base_feature: str,
    chamfer_name: str,
    size: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> object:
    return _call(
        conn,
        "chamfer_feature",
        {
            "doc_name": doc_name,
            "base_feature": base_feature,
            "chamfer_name": chamfer_name,
            "size": size,
            "edge_refs": edge_refs,
            "body_name": body_name,
        },
        "Chamfer feature",
    )


def fillet_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    base_feature: str,
    fillet_name: str,
    radius: float,
    edge_refs: list[str] | None = None,
    body_name: str | None = None,
) -> object:
    return _call(
        conn,
        "fillet_feature",
        {
            "doc_name": doc_name,
            "base_feature": base_feature,
            "fillet_name": fillet_name,
            "radius": radius,
            "edge_refs": edge_refs,
            "body_name": body_name,
        },
        "Fillet feature",
    )


def helical_sweep_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    profile_sketch: str,
    helix_name: str,
    pitch: float,
    height: float,
    radius: float,
    body_name: str | None = None,
    left_handed: bool = False,
    reversed_dir: bool = False,
) -> object:
    return _call(
        conn,
        "helical_sweep_feature",
        {
            "doc_name": doc_name,
            "profile_sketch": profile_sketch,
            "helix_name": helix_name,
            "pitch": pitch,
            "height": height,
            "radius": radius,
            "body_name": body_name,
            "left_handed": left_handed,
            "reversed_dir": reversed_dir,
        },
        "Helical sweep feature",
    )


def linear_pattern_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    length: float,
    occurrences: int,
    direction: str = "X_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> object:
    return _call(
        conn,
        "linear_pattern_feature",
        {
            "doc_name": doc_name,
            "feature_name": feature_name,
            "pattern_name": pattern_name,
            "length": length,
            "occurrences": occurrences,
            "direction": direction,
            "body_name": body_name,
            "reversed_dir": reversed_dir,
        },
        "Linear pattern feature",
    )


def loft_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    sketch_names: list[str],
    loft_name: str,
    body_name: str | None = None,
    ruled: bool = False,
    closed: bool = False,
) -> object:
    return _call(
        conn,
        "loft_feature",
        {
            "doc_name": doc_name,
            "sketch_names": sketch_names,
            "loft_name": loft_name,
            "body_name": body_name,
            "ruled": ruled,
            "closed": closed,
        },
        "Loft feature",
    )


def mirror_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    feature_name: str,
    mirror_name: str,
    plane: str = "YZ_Plane",
    body_name: str | None = None,
) -> object:
    return _call(
        conn,
        "mirror_feature",
        {
            "doc_name": doc_name,
            "feature_name": feature_name,
            "mirror_name": mirror_name,
            "plane": plane,
            "body_name": body_name,
        },
        "Mirror feature",
    )


def polar_pattern_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    occurrences: int,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> object:
    return _call(
        conn,
        "polar_pattern_feature",
        {
            "doc_name": doc_name,
            "feature_name": feature_name,
            "pattern_name": pattern_name,
            "occurrences": occurrences,
            "angle": angle,
            "axis": axis,
            "body_name": body_name,
            "reversed_dir": reversed_dir,
        },
        "Polar pattern feature",
    )


def revolve_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    sketch_name: str,
    revolve_name: str,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> object:
    return _call(
        conn,
        "revolve_feature",
        {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "revolve_name": revolve_name,
            "angle": angle,
            "axis": axis,
            "body_name": body_name,
            "symmetric": symmetric,
            "reversed_dir": reversed_dir,
        },
        "Revolve feature",
    )


def sweep_feature(
    conn: _TypedFeatureConnection,
    doc_name: str,
    profile_sketch: str,
    path_sketch: str,
    sweep_name: str,
    body_name: str | None = None,
    frenet: bool = False,
) -> object:
    return _call(
        conn,
        "sweep_feature",
        {
            "doc_name": doc_name,
            "profile_sketch": profile_sketch,
            "path_sketch": path_sketch,
            "sweep_name": sweep_name,
            "body_name": body_name,
            "frenet": frenet,
        },
        "Sweep feature",
    )


_RPC_METHODS = (
    boolean_difference,
    boolean_intersection,
    boolean_union,
    chamfer_feature,
    fillet_feature,
    helical_sweep_feature,
    linear_pattern_feature,
    loft_feature,
    mirror_feature,
    polar_pattern_feature,
    revolve_feature,
    sweep_feature,
)


def attach_p3_feature_rpc(connection_type: type[object]) -> None:
    """Bind typed JSON-RPC methods without editing facade_bindings."""

    for method in _RPC_METHODS:
        setattr(connection_type, method.__name__, method)


__all__ = [
    "attach_p3_feature_rpc",
    "invoke_typed_feature_rpc",
]
