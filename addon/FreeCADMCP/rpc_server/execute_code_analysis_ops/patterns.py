"""Typed-tool pattern tables for execute_code analysis."""

from __future__ import annotations

_TYPED_PATTERNS = {
    "recompute": "recompute_document",
    "save": "save_document",
    "saveas": "save_document_as",
    "removeobject": "delete_object",
    "setexpression": "set_expression",
    "addconstraint": "sketch_add_constraint",
    "addgeometry": "sketch_add_geometry",
    "delconstraint": "sketch_delete_constraint",
    "delconstraints": "sketch_delete_constraint",
    "delgeometry": "sketch_delete_geometry",
    "delgeometries": "sketch_delete_geometry",
}

_TYPE_PATTERNS = {
    "PartDesign::Body": "body_create",
    "Sketcher::SketchObject": "sketch_create",
    "Spreadsheet::Sheet": "spreadsheet_create",
    "PartDesign::Feature": "create_object",
}


def typed_pattern_for_call(call: str) -> str | None:
    return _TYPED_PATTERNS.get(call.rsplit(".", 1)[-1].lower())


def typed_pattern_for_type_id(type_id: str) -> str | None:
    return _TYPE_PATTERNS.get(type_id)
