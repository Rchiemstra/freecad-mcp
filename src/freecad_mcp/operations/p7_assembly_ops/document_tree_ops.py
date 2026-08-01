from __future__ import annotations

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse
from ...template_resources import render_template_lines, render_template_text
from .helpers import (
    _doc_preamble,
    _run_json_code,
    _shared_helpers,
    _validate_if_exists,
)


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/get_document_tree.py.txt",
        root_filter=repr(root_filter),
        max_depth=repr(max_depth),
        include=repr(include),
        include_properties=repr(include_properties),
        selected_nodes=repr(selected_nodes),
    )
    return _run_json_code(
        freecad,
        True,
        "\n".join(lines),
        "Failed to get document tree",
        document=doc_name,
        read_only=True,
    )

def create_part_container_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/create_part_container.py.txt",
        part_name=repr(part_name),
        parent_container=repr(parent_container),
        if_exists=repr(if_exists),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create part container",
        screenshot=True,
        document=doc_name,
    )

def move_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    target_container: str,
    remove_from_old_parent: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + render_template_lines(
        "p7_assembly/move_object.py.txt",
        obj_name=repr(obj_name),
        target_container=repr(target_container),
        remove_from_old_parent=repr(remove_from_old_parent),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to move object",
        screenshot=True,
        document=doc_name,
    )

def create_subshape_binder_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    binder_name: str,
    source_object: str,
    sub_elements: list[str] | None = None,
    target_body: str | None = None,
    target_container: str | None = None,
    relative: bool = False,
    sync_placement: bool = True,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    binder_code = render_template_text(
        "p7_assembly/create_subshape_binder.py.txt",
        binder_name=repr(binder_name),
        source_name=repr(source_object),
        subs=repr(sub_elements),
        target_body_name=repr(target_body),
        target_container_name=repr(target_container),
        relative=repr(relative),
        sync_placement=repr(sync_placement),
        if_exists=repr(if_exists),
    )
    lines = [
        *_doc_preamble(doc_name),
        *_shared_helpers(),
        *binder_code.strip().splitlines(),
        *render_template_lines(
            "diagnostics/cross_body_preflight.py.txt",
            obj_name=repr(binder_name),
        ),
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create subshape binder",
        screenshot=True,
        document=doc_name,
    )

def create_datum_plane_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    plane_name: str,
    body_name: str,
    mode: str,
    source_ref: str | None = None,
    face_a: str | None = None,
    face_b: str | None = None,
    offset_along_normal: list[float] | None = None,
    map_mode: str = "FlatFace",
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = [
        *_doc_preamble(doc_name),
        *_shared_helpers(),
        *render_template_lines(
            "p7_assembly/create_datum_plane.py.txt",
            plane_name=repr(plane_name),
            body_name=repr(body_name),
            mode=repr(mode),
            source_ref=repr(source_ref),
            face_a=repr(face_a),
            face_b=repr(face_b),
            offset_along_normal=repr(offset_along_normal),
            map_mode=repr(map_mode),
            if_exists=repr(if_exists),
        ),
        *render_template_lines(
            "diagnostics/cross_body_preflight.py.txt",
            obj_name=repr(plane_name),
        ),
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create datum plane",
        screenshot=True,
        document=doc_name,
    )
