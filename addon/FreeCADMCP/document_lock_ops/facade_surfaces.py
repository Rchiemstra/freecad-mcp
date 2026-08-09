"""Late-bound surfaces that tests monkeypatch through the document_lock facade."""

from __future__ import annotations

import time as _stdlib_time
from collections.abc import Callable
from types import ModuleType
from typing import Any

_facade_bindings: list[dict[str, Any]] = []


def configure_facade_surfaces(
    *,
    time_module_provider: Callable[[], ModuleType],
    settings_path_provider: Callable[[], Any],
    pid_alive_provider: Callable[[int], bool],
    facade_namespace: dict[str, Any] | None = None,
    default_settings_path: Any = None,
    default_pid_alive: Any = None,
) -> None:
    """Bind compatibility seams explicitly from the document-lock façade."""

    binding = {
        "namespace": facade_namespace,
        "default_time": (
            facade_namespace.get("time")
            if facade_namespace is not None
            else _stdlib_time
        ),
        "time_provider": time_module_provider,
        "settings_path_provider": settings_path_provider,
        "pid_alive_provider": pid_alive_provider,
        "default_settings_path": default_settings_path,
        "default_pid_alive": default_pid_alive,
    }
    for existing in _facade_bindings:
        if existing["namespace"] is facade_namespace and facade_namespace is not None:
            existing.update(binding)
            return
    _facade_bindings.append(binding)


def _modified_facade_value(name: str, default_key: str) -> Any | None:
    for binding in reversed(_facade_bindings):
        namespace = binding["namespace"]
        if namespace is None:
            continue
        candidate = namespace.get(name)
        if candidate is not None and candidate is not binding[default_key]:
            return candidate
    return None


def time_module() -> ModuleType:
    modified = _modified_facade_value("time", "default_time")
    if modified is not None:
        return modified
    if _facade_bindings:
        return _facade_bindings[-1]["time_provider"]()
    return _stdlib_time


def current_time() -> float:
    return time_module().time()


def resolve_settings_path():
    modified = _modified_facade_value(
        "_settings_path", "default_settings_path"
    )
    if callable(modified):
        return modified()
    if _facade_bindings:
        return _facade_bindings[-1]["settings_path_provider"]()
    from .settings import _settings_path_impl

    return _settings_path_impl()


def resolve_pid_alive(pid: int) -> bool:
    modified = _modified_facade_value("pid_alive", "default_pid_alive")
    if callable(modified):
        return bool(modified(pid))
    if _facade_bindings:
        return bool(_facade_bindings[-1]["pid_alive_provider"](pid))
    from .file_baseline import pid_alive_impl

    return pid_alive_impl(pid)
