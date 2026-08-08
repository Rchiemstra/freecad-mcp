"""Guarded GUI dispatch and public failure shaping for personal contexts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .collaboration_context_core import (
    _member,
    collaborators,
    redacted_error,
)

_GUI_CALLBACK_VALUE_KEY = "_freecad_mcp_gui_callback_value"
_GUI_CALLBACK_VALUE_VERSION = "v1"


def _callback_value(value: Any) -> dict[str, Any]:
    """Wrap a successful callback in a replay-journal-safe envelope."""

    return {
        _GUI_CALLBACK_VALUE_KEY: _GUI_CALLBACK_VALUE_VERSION,
        "value": value,
    }


def _is_callback_value(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get(_GUI_CALLBACK_VALUE_KEY) == _GUI_CALLBACK_VALUE_VERSION
        and "value" in value
    )


def _callback_error_code(error: Exception) -> str:
    return str(getattr(error, "code", type(error).__name__.upper()))


class GuiDispatchFailure(RuntimeError):
    """Exact structured failure returned by the production GUI dispatcher."""

    def __init__(self, result: Mapping[str, Any]):
        self.result = dict(result)
        for name in (
            "error_code",
            "request_id",
            "timeout_stage",
            "execution_started",
            "mutation_started",
            "completion_uncertain",
            "recovery_incident_id",
        ):
            setattr(self, name, self.result.get(name))
        super().__init__(str(self.result.get("error") or "GUI dispatch failed"))


def _unwrap_callback_value(result: Any) -> Any:
    if isinstance(result, Mapping) and result.get("success") is False:
        return result
    if isinstance(result, Mapping) and result.get("ok") is False:
        return result
    if isinstance(result, Mapping) and _is_callback_value(result.get("result")):
        result = result["result"]
    if _is_callback_value(result):
        return result["value"]
    raise RuntimeError("GUI dispatcher returned an invalid callback envelope")


def dispatch_gui(
    facade: Any,
    callback: Callable[[], Any],
    *,
    late_result_transform: Callable[[Any], Any] | None = None,
    journal_late_completion: bool = True,
) -> Any:
    callback_error = None

    def guarded_callback() -> dict[str, Any]:
        nonlocal callback_error
        try:
            return _callback_value(callback())
        except Exception as exc:
            callback_error = exc
            return {
                "success": False,
                "error_code": _callback_error_code(exc),
                "error": str(exc),
            }

    def finalize_late_result(value: Any) -> Any:
        value = _unwrap_callback_value(value)
        if late_result_transform is not None:
            return late_result_transform(value)
        return value

    result = _member(collaborators(facade), "dispatch_gui")(
        facade,
        guarded_callback,
        late_result_transform=finalize_late_result,
        journal_late_completion=journal_late_completion,
    )
    if isinstance(result, Mapping) and result.get("success") is False:
        if isinstance(callback_error, Exception) and result.get(
            "error_code"
        ) == _callback_error_code(callback_error):
            raise callback_error
        raise GuiDispatchFailure(result)
    return _unwrap_callback_value(result)


def public_error(facade: Any, exc: Exception, **defaults: Any) -> dict[str, Any]:
    if isinstance(exc, GuiDispatchFailure):
        result = dict(exc.result)
        result.setdefault("ok", False)
        for name, value in defaults.items():
            result.setdefault(name, value)
        return result
    result = {"ok": False, "error": redacted_error(facade, exc), **defaults}
    error_code = getattr(exc, "code", None)
    if error_code:
        result["success"] = False
        result["error_code"] = str(error_code)
    return result


__all__ = [
    "GuiDispatchFailure",
    "_unwrap_callback_value",
    "dispatch_gui",
    "public_error",
]
