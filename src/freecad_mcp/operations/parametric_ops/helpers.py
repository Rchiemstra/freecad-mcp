from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...freecad_client import FreeCADConnection
from ...responses import ToolResponse, tool_fail, tool_ok
from ...template_resources import (
    read_template_text,
    render_template_lines,
)
from ..p7_assembly import _run_json_code


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
