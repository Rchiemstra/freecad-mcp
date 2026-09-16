from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...responses.tool_results import tool_fail, tool_ok


def _doc_missing(doc_name: str) -> str:
    return repr(f"Document {doc_name!r} not found")


def _typed_rpc_unavailable(exc: BaseException) -> bool:
    """True only when the addon/client lacks the typed method entirely."""
    if isinstance(exc, AttributeError):
        return True
    text = str(exc).lower()
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
    return "sketch_attach" in text and any(
        token in text for token in ("not supported", "not found", "no method")
    )


def _typed_rpc_unavailable_result(result: Any) -> bool:
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
            'method "sketch_attach" is not supported',
            "unknown method",
        )
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
