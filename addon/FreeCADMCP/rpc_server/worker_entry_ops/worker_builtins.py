"""Guard worker jobs against FreeCADGui imports."""

from __future__ import annotations

import builtins

from ..worker_protocol_types.unsupported_worker_gui_error import UnsupportedWorkerGuiError


def worker_builtins():
    """Reject GUI imports through the supported worker API (not a sandbox)."""
    namespace = dict(vars(builtins))
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if str(name).split(".", 1)[0] == "FreeCADGui":
            raise UnsupportedWorkerGuiError("FreeCADGui is unsupported in worker jobs")
        return original_import(name, globals, locals, fromlist, level)

    namespace["__import__"] = guarded_import
    return namespace
