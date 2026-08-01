from __future__ import annotations

import sys
from typing import Any


def facade_callable(name: str, default: Any) -> Any:
    for module_name in ("addon.FreeCADMCP.lock_indicator", "lock_indicator"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            return getattr(module, name)
    return default


def facade_attr(name: str) -> Any | None:
    for module_name in ("addon.FreeCADMCP.lock_indicator", "lock_indicator"):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, name):
            return getattr(module, name)
    return None
