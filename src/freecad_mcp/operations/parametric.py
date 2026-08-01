"""Parametric PartDesign helpers — Spreadsheet, expressions, Body/attach, diagnostics.

These tools close the gap between geometry automation (sketch/pad) and live
parameter-driven design (Spreadsheet aliases → property/constraint expressions).

Most ops still use signed generated ``execute_code`` templates for addon
compatibility. ``sketch_attach`` prefers the authenticated typed RPC method and
only falls back to generated Python when that method is unavailable on the
connected addon — never after a real typed-operation failure.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, tool_fail, tool_ok
from ..template_resources import read_template_text, render_template_lines
from .p7_assembly import _run_json_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_missing(doc_name: str) -> str:
    return repr(f"Document {doc_name!r} not found")


def _typed_rpc_unavailable(exc: BaseException) -> bool:
    """True only when the addon/client lacks the typed method entirely."""
    if isinstance(exc, AttributeError):
        return True
    text = str(exc).lower()
    # Require a method-missing signal, not merely the method name in an
    # application error (e.g. "Sketch not found" must NOT fall back).
    missing_signals = (
        "method not found",
        "is not supported",
        "there is no method",
        "unknown method",
        "has no attribute",
        "invalid method name",
        "attributeerror",
    )
    if any(signal in text for signal in missing_signals):
        return True
    # xmlrpc.client.Fault often embeds "method \"sketch_attach\" is not supported"
    return "sketch_attach" in text and any(
        token in text for token in ("not supported", "not found", "no method")
    )


def _typed_rpc_unavailable_result(result: Any) -> bool:
    """Recognize an authenticated response proving the RPC method is absent.

    Protocol-v2 returns capability errors as data rather than raising them.
    Fall back only for explicit method-absence codes; ambiguous protocol or
    application failures remain terminal so a possibly-started mutation is
    never retried through generated code.
    """
    if not isinstance(result, Mapping):
        return False

    error = result.get("error")
    nested_error = error if isinstance(error, Mapping) else {}
    code = str(
        result.get("error_code")
        or result.get("code")
        or nested_error.get("code")
        or ""
    ).upper()
    message = str(
        nested_error.get("message")
        or (error if not isinstance(error, Mapping) else "")
        or result.get("message")
        or ""
    ).lower()

    if code in {"UNKNOWN_METHOD", "METHOD_NOT_FOUND", "RPC_METHOD_NOT_FOUND"}:
        return True
    return code == "RPC_V2_ERROR" and any(
        signal in message
        for signal in (
            "method not found",
            "method is not supported",
            "method \"sketch_attach\" is not supported",
            "unknown method",
        )
    )


def _generated_sketch_attach(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    support: str | dict[str, Any],
    attachment_offset: dict[str, Any] | None,
) -> ToolResponse:
    """Compatibility path for addons without typed ``sketch_attach``."""
    lines = render_template_lines(
        "parametric/sketch_attach.py.txt",
        doc_name=repr(doc_name),
        doc_missing=_doc_missing(doc_name),
        sketch_name=repr(sketch_name),
        support=repr(support),
        attachment_offset=repr(attachment_offset),
        placement_helpers=read_template_text(
            "parametric/placement_helpers.py.txt"
        ).strip(),
    )
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to attach sketch",
        screenshot=False,
        document=doc_name,
    )


def _typed_sketch_attach_result(
    res: Any,
    *,
    only_text_feedback: bool,
) -> ToolResponse:
    if isinstance(res, str):
        return tool_fail(f"Failed to attach sketch: {res}")
    if not isinstance(res, dict):
        return tool_fail(
            f"Failed to attach sketch: unexpected typed response {type(res)!r}"
        )
    failed = res.get("success") is False or res.get("ok") is False
    if failed or res.get("error") or res.get("error_code"):
        return tool_fail(
            f"Failed to attach sketch: {res.get('error') or res}",
            structured=res,
            error_code=res.get("error_code"),
        )
    sketch = res.get("sketch") or res.get("sketch_name") or ""
    return tool_ok(
        f"Sketch '{sketch}' attached successfully",
        structured=res,
        only_text_feedback=only_text_feedback,
    )


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
    attachment_offset: dict[str, Any] | None = None,
) -> ToolResponse:
    """Attach a sketch via typed RPC; generated code only if RPC is missing."""
    typed = getattr(freecad, "sketch_attach", None)
    if attachment_offset is not None:
        capability_probe = getattr(freecad, "supports_rpc_parameter", None)
        if callable(capability_probe):
            try:
                offset_supported = capability_probe(
                    "sketch_attach", "attachment_offset"
                )
            except Exception as exc:
                logger.warning(
                    "Could not inspect sketch_attach capabilities: %s", exc
                )
            else:
                if offset_supported is False:
                    logger.info(
                        "Addon predates sketch_attach attachment_offset; using "
                        "generated fallback before mutation"
                    )
                    typed = None
    if callable(typed):
        try:
            # Compatibility: omit fourth arg when unused (older XML-RPC signatures).
            if attachment_offset is None:
                res = typed(doc_name, sketch_name, support)
            else:
                res = typed(doc_name, sketch_name, support, attachment_offset)
        except Exception as exc:
            if not _typed_rpc_unavailable(exc):
                logger.error("Typed sketch_attach failed: %s", exc)
                return tool_fail(f"Failed to attach sketch: {exc}")
            logger.info(
                "Typed sketch_attach unavailable (%s); using generated fallback",
                exc,
            )
        else:
            if not _typed_rpc_unavailable_result(res):
                # Typed path answered — never retry after a real failure.
                return _typed_sketch_attach_result(
                    res, only_text_feedback=only_text_feedback
                )
            logger.info(
                "Typed sketch_attach is absent in the authenticated addon; "
                "using generated fallback"
            )

    return _generated_sketch_attach(
        freecad,
        only_text_feedback,
        doc_name,
        sketch_name,
        support,
        attachment_offset,
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
