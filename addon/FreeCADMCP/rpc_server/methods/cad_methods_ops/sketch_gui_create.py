"""Sketch create/attach GUI handlers (Phase 4 slice 4F)."""

from __future__ import annotations

from .sketch_attach_helpers import resolve_sketch_support
from .sketch_create_helpers import apply_create_attach_to, create_sketch_object


def sketch_create_gui(
    doc_name,
    sketch_name,
    body_name,
    attach_to,
    *,
    freecad,
    recompute: bool = True,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."

        sketch, error = create_sketch_object(doc, sketch_name, body_name)
        if error:
            return error

        if attach_to:
            attach_error = apply_create_attach_to(
                sketch, doc, attach_to, freecad=freecad
            )
            if attach_error:
                return attach_error

        if recompute:
            doc.recompute()
        freecad.Console.PrintMessage(
            f"Sketch '{sketch_name}' created in '{doc_name}'.\n"
        )
        return True
    except Exception as e:
        return str(e)


def sketch_attach_gui(
    doc_name,
    sketch_name,
    support,
    attachment_offset=None,
    *,
    freecad,
    dict_to_placement,
    placement_to_dict,
    recompute: bool = True,
):
    try:
        doc = freecad.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sketch = doc.getObject(sketch_name)
        if not sketch:
            return f"Sketch '{sketch_name}' not found."

        attached, error = resolve_sketch_support(sketch, doc, support)
        if error:
            return error

        offset_error = _apply_attachment_offset(
            sketch,
            sketch_name,
            attachment_offset,
            dict_to_placement=dict_to_placement,
        )
        if offset_error:
            return offset_error

        if recompute:
            doc.recompute()
        return _sketch_attach_result(
            sketch,
            attached,
            attachment_offset,
            placement_to_dict=placement_to_dict,
        )
    except Exception as e:
        return str(e)


def _apply_attachment_offset(
    sketch, sketch_name, attachment_offset, *, dict_to_placement
):
    if attachment_offset is None:
        return None
    if not hasattr(sketch, "AttachmentOffset"):
        return f"Sketch '{sketch_name}' has no AttachmentOffset property."
    sketch.AttachmentOffset = dict_to_placement(attachment_offset)
    return None


def _sketch_attach_result(sketch, attached, attachment_offset, *, placement_to_dict):
    result = {"success": True, "sketch": sketch.Name, "attached": attached}
    if attachment_offset is not None and hasattr(sketch, "AttachmentOffset"):
        result["attachment_offset"] = placement_to_dict(sketch.AttachmentOffset)
    return result
