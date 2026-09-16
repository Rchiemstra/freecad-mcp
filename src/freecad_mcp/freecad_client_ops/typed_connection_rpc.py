"""JSON-RPC client helpers for typed connection mutations outside facade census."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class _TypedConnection(Protocol):
    def _invoke_mutation_v2(
        self,
        method: str,
        params: Mapping[str, object],
        *,
        document_names: tuple[str, ...] = (),
        operation_name: str | None = None,
    ) -> object: ...


_UNCERTAIN_FALLBACK: dict[str, object] = {
    "contract_version": 1,
    "success": False,
    "ok": False,
    "outcome": "uncertain",
    "committed": None,
    "retry_safe": False,
    "error_code": "INVALID_RPC_RESPONSE",
    "error": "typed RPC v2 context is unavailable",
}


def _invoke(
    conn: _TypedConnection,
    method: str,
    params: Mapping[str, object],
    *,
    operation_name: str,
) -> object:
    doc_name = params.get("doc_name")
    document_names = (str(doc_name),) if isinstance(doc_name, str) and doc_name else ()
    routed = conn._invoke_mutation_v2(
        method,
        params,
        document_names=document_names,
        operation_name=operation_name,
    )
    if routed is not None:
        return routed
    return dict(_UNCERTAIN_FALLBACK)


def create_datum_plane(
    conn: _TypedConnection,
    doc_name: str,
    plane_name: str,
    body_name: str,
    mode: str,
    source_ref: str | None = None,
    face_a: str | None = None,
    face_b: str | None = None,
    offset_along_normal: object = None,
    map_mode: str = "FlatFace",
    if_exists: str = "error",
) -> object:
    return _invoke(
        conn,
        "create_datum_plane",
        {
            "doc_name": doc_name,
            "plane_name": plane_name,
            "body_name": body_name,
            "mode": mode,
            "source_ref": source_ref,
            "face_a": face_a,
            "face_b": face_b,
            "offset_along_normal": offset_along_normal,
            "map_mode": map_mode,
            "if_exists": if_exists,
        },
        operation_name="Create datum plane",
    )


def create_part_container(
    conn: _TypedConnection,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: str = "error",
) -> object:
    return _invoke(
        conn,
        "create_part_container",
        {
            "doc_name": doc_name,
            "part_name": part_name,
            "parent_container": parent_container,
            "if_exists": if_exists,
        },
        operation_name="Create part container",
    )


def create_placement_binder(
    conn: _TypedConnection,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    bind_mode: str = "Synchronized",
) -> object:
    return _invoke(
        conn,
        "create_placement_binder",
        {
            "doc_name": doc_name,
            "owner_body": owner_body,
            "name": name,
            "source": source,
            "relative": relative,
            "bind_mode": bind_mode,
        },
        operation_name="Create placement binder",
    )


def create_placement_datum(
    conn: _TypedConnection,
    doc_name: str,
    owner_body: str,
    name: str,
    source: str,
    relative: bool = True,
    offset: object = None,
) -> object:
    return _invoke(
        conn,
        "create_placement_datum",
        {
            "doc_name": doc_name,
            "owner_body": owner_body,
            "name": name,
            "source": source,
            "relative": relative,
            "offset": offset,
        },
        operation_name="Create placement datum",
    )


def create_subshape_binder(
    conn: _TypedConnection,
    doc_name: str,
    binder_name: str,
    source_object: str,
    sub_elements: object = None,
    target_body: str | None = None,
    target_container: str | None = None,
    relative: bool = False,
    sync_placement: bool = True,
    if_exists: str = "error",
) -> object:
    return _invoke(
        conn,
        "create_subshape_binder",
        {
            "doc_name": doc_name,
            "binder_name": binder_name,
            "source_object": source_object,
            "sub_elements": sub_elements,
            "target_body": target_body,
            "target_container": target_container,
            "relative": relative,
            "sync_placement": sync_placement,
            "if_exists": if_exists,
        },
        operation_name="Create subshape binder",
    )


def move_object(
    conn: _TypedConnection,
    doc_name: str,
    obj_name: str,
    target_container: str,
    remove_from_old_parent: bool = True,
) -> object:
    return _invoke(
        conn,
        "move_object",
        {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "target_container": target_container,
            "remove_from_old_parent": remove_from_old_parent,
        },
        operation_name="Move object",
    )


def preview_attachment(
    conn: _TypedConnection,
    doc_name: str,
    datum_name: str,
) -> object:
    return _invoke(
        conn,
        "preview_attachment",
        {"doc_name": doc_name, "datum_name": datum_name},
        operation_name="Preview attachment",
    )


def sketch_add_external_projection(
    conn: _TypedConnection,
    doc_name: str,
    sketch_name: str,
    source_ref: str,
    projection_mode: str = "auto",
    defining: bool = False,
    allow_gui_geometry_loop: bool = False,
) -> object:
    return _invoke(
        conn,
        "sketch_add_external_projection",
        {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "source_ref": source_ref,
            "projection_mode": projection_mode,
            "defining": defining,
            "allow_gui_geometry_loop": allow_gui_geometry_loop,
        },
        operation_name="Add sketch external projection",
    )


def build_path_wire(
    conn: _TypedConnection,
    doc_name: str,
    wire_name: str,
    segments: object,
    tolerance_mm: float = 0.5,
    container: str | None = None,
    if_exists: str = "error",
) -> object:
    return _invoke(
        conn,
        "build_path_wire",
        {
            "doc_name": doc_name,
            "wire_name": wire_name,
            "segments": segments,
            "tolerance_mm": tolerance_mm,
            "container": container,
            "if_exists": if_exists,
        },
        operation_name="Build path wire",
    )


def sweep_pipe(
    conn: _TypedConnection,
    doc_name: str,
    path_wire: str,
    diameter_mm: float,
    solid_name: str,
    profile_mode: str = "frenet",
    color: object = None,
    container: str | None = None,
    if_exists: str = "error",
) -> object:
    return _invoke(
        conn,
        "sweep_pipe",
        {
            "doc_name": doc_name,
            "path_wire": path_wire,
            "diameter_mm": diameter_mm,
            "solid_name": solid_name,
            "profile_mode": profile_mode,
            "color": color,
            "container": container,
            "if_exists": if_exists,
        },
        operation_name="Sweep pipe",
    )


def restore(
    conn: _TypedConnection,
    doc_name: str,
    snapshot_id: str | None = None,
) -> object:
    return _invoke(
        conn,
        "restore",
        {"doc_name": doc_name, "snapshot_id": snapshot_id},
        operation_name="Restore snapshot",
    )


def relink_references(
    conn: _TypedConnection,
    doc_name: str,
    from_obj: str,
    to_obj: str,
) -> object:
    return _invoke(
        conn,
        "relink_references",
        {"doc_name": doc_name, "from_obj": from_obj, "to_obj": to_obj},
        operation_name="Relink references",
    )


def validate_movement_follow(
    conn: _TypedConnection,
    doc_name: str,
    source: str,
    dependents: object,
    translation: object,
    axis: object,
    angle_deg: float,
    restore: bool = True,
    tolerance: float = 1e-07,
) -> object:
    return _invoke(
        conn,
        "validate_movement_follow",
        {
            "doc_name": doc_name,
            "source": source,
            "dependents": dependents,
            "translation": translation,
            "axis": axis,
            "angle_deg": angle_deg,
            "restore": restore,
            "tolerance": tolerance,
        },
        operation_name="Validate movement follow",
    )


_RPC_METHODS = (
    build_path_wire,
    create_datum_plane,
    create_part_container,
    create_placement_binder,
    create_placement_datum,
    create_subshape_binder,
    move_object,
    preview_attachment,
    sketch_add_external_projection,
    sweep_pipe,
    restore,
    relink_references,
    validate_movement_follow,
)


def attach_connection_rpc(connection_type: type[object]) -> None:
    """Bind typed JSON-RPC methods without editing facade_bindings."""

    for method in _RPC_METHODS:
        setattr(connection_type, method.__name__, method)


__all__ = [
    "attach_connection_rpc",
]
