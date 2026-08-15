from __future__ import annotations

from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import tool_fail
from ...template_resources import render_template_lines
from ..p7_assembly import _run_json_code
from .helpers import _doc_missing, _typed_parametric_mutation


def spreadsheet_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sheet_name: str,
) -> ToolResponse:
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "spreadsheet_create",
        (doc_name, sheet_name),
        "Failed to create spreadsheet",
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
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "spreadsheet_set_cells",
        (doc_name, sheet_name, cells),
        "Failed to set spreadsheet cells",
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
    return _typed_parametric_mutation(
        freecad,
        only_text_feedback,
        "spreadsheet_set_alias",
        (doc_name, sheet_name, address, alias),
        "Failed to set spreadsheet alias",
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
