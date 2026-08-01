"""Late-bound surfaces that tests monkeypatch through the document_lock facade."""

from __future__ import annotations

import time as _stdlib_time
from types import ModuleType

_FACADE_NAMES = ("document_lock", "addon.FreeCADMCP.document_lock")


def _facade_module():
    import sys

    for name in _FACADE_NAMES:
        module = sys.modules.get(name)
        if module is not None:
            return module
    return None


def time_module() -> ModuleType:
    facade = _facade_module()
    if facade is not None and hasattr(facade, "time"):
        return facade.time
    return _stdlib_time


def current_time() -> float:
    return time_module().time()


def resolve_settings_path():
    facade = _facade_module()
    if facade is not None:
        candidate = getattr(facade, "_settings_path", None)
        if candidate is not None:
            return candidate()
    from .settings import _settings_path_impl

    return _settings_path_impl()


def resolve_pid_alive(pid: int) -> bool:
    facade = _facade_module()
    if facade is not None:
        candidate = getattr(facade, "pid_alive", None)
        if candidate is not None:
            return candidate(pid)
    from .file_baseline import pid_alive_impl

    return pid_alive_impl(pid)
