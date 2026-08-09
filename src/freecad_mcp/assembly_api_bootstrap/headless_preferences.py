# SPDX-License-Identifier: LGPL-2.1-or-later

import types
from collections.abc import MutableMapping

import FreeCAD as App

_module_registry: MutableMapping[str, object] | None = None


def bind_headless_module_registry(
    module_registry: MutableMapping[str, object],
) -> None:
    global _module_registry
    _module_registry = module_registry


def ensure_headless_preferences_shim(
    *, module_registry: MutableMapping[str, object] | None = None
):
    if App.GuiUp:
        return
    registry = _module_registry if module_registry is None else module_registry
    if registry is None:
        raise RuntimeError("headless module registry was not injected at bootstrap")

    preferences_module = types.ModuleType("Preferences")
    preferences_module.preferences = lambda: App.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/Assembly"
    )
    registry.setdefault("Preferences", preferences_module)
