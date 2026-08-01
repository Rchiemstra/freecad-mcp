# SPDX-License-Identifier: LGPL-2.1-or-later

import sys
import types

import FreeCAD as App


def ensure_headless_preferences_shim():
    if App.GuiUp or "Preferences" in sys.modules:
        return

    preferences_module = types.ModuleType("Preferences")
    preferences_module.preferences = lambda: App.ParamGet(
        "User parameter:BaseApp/Preferences/Mod/Assembly"
    )
    sys.modules["Preferences"] = preferences_module
