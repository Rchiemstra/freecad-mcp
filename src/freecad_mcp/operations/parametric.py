"""Parametric PartDesign helpers — Spreadsheet, expressions, Body/attach, diagnostics.

These tools close the gap between geometry automation (sketch/pad) and live
parameter-driven design (Spreadsheet aliases → property/constraint expressions).
All ops use execute_code templates so they work without an addon Mod sync.
"""
from __future__ import annotations

import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, tool_fail
from ..template_resources import render_template_lines
from .p7_assembly import _run_json_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_missing(doc_name: str) -> str:
    return repr(f"Document {doc_name!r} not found")


def spreadsheet_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/spreadsheet_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sheet_name=repr(sheet_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create spreadsheet",
        screenshot=False,
        document=doc_name,
    )


def spreadsheet_set_cells_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
    cells: list[dict[str, Any]],
) -> ToolResponse:
    if not isinstance(cells, list) or not cells:
        return tool_fail("cells must be a non-empty list of {address|alias, value, ...}")
    lines = render_template_lines(
        "parametric/spreadsheet_set_cells.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sheet_name=repr(sheet_name),
        cells=repr(cells),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set spreadsheet cells",
        screenshot=False,
        document=doc_name,
    )


def spreadsheet_get_cells_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
    addresses: list[Any],
) -> ToolResponse:
    if not isinstance(addresses, list) or not addresses:
        return tool_fail("addresses must be a non-empty list of addresses or {address|alias}")
    lines = render_template_lines(
        "parametric/spreadsheet_get_cells.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sheet_name=repr(sheet_name),
        addresses=repr(addresses),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to get spreadsheet cells",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def spreadsheet_set_alias_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
    address: str,
    alias: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/spreadsheet_set_alias.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sheet_name=repr(sheet_name),
        address=repr(address),
        alias=repr(alias),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set spreadsheet alias",
        screenshot=False,
        document=doc_name,
    )


def spreadsheet_list_aliases_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/spreadsheet_list_aliases.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sheet_name=repr(sheet_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to list spreadsheet aliases",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def set_expression_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    prop_path: str,
    expression: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/set_expression.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
        prop_path=repr(prop_path),
        expression=repr(expression),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set expression",
        screenshot=False,
        document=doc_name,
    )


def clear_expression_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
    prop_path: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/clear_expression.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
        prop_path=repr(prop_path),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to clear expression",
        screenshot=False,
        document=doc_name,
    )


def list_expressions_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/list_expressions.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to list expressions",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )


def body_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/body_create.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        body_name=repr(body_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create body",
        screenshot=False,
        document=doc_name,
    )


def body_set_tip_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    body_name: str,
    feature_name: str,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/body_set_tip.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        body_name=repr(body_name),
        feature_name=repr(feature_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to set body tip",
        screenshot=False,
        document=doc_name,
    )


def sketch_attach_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | dict[str, Any],
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/sketch_attach.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sketch_name=repr(sketch_name),
        support=repr(support),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to attach sketch",
        screenshot=False,
        document=doc_name,
    )


def sketch_edit_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    value: float | None = None,
    name: str | None = None,
    index: int | None = None,
) -> ToolResponse:
    if name is None and index is None:
        return tool_fail("Provide constraint name=... or index=... (prefer name after trim/fillet)")
    lines = render_template_lines(
        "parametric/sketch_edit_constraint.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sketch_name=repr(sketch_name),
        constraint_name=repr(name),
        constraint_index=repr(index),
        value=repr(value),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to edit constraint",
        screenshot=False,
        document=doc_name,
    )


def diagnose_parametric_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    object_name: str | None = None,
) -> ToolResponse:
    lines = render_template_lines(
        "parametric/diagnose_parametric.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        object_name=repr(object_name),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to diagnose parametric model",
        screenshot=False,
        document=doc_name,
        read_only=True,
    )
