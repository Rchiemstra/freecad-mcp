from __future__ import annotations

# ruff: noqa: F403
from ._support import *

"""RPC dispatch chokepoint after native collaboration cutover."""


def dispatch(self, method, params):
    """Dispatch without creating a second document-authority layer.

    JSON-RPC v2 authenticates its immutable envelope in ``invoke_v2``.  CAD
    mutation methods enter FreeCAD's native compatibility-commit boundary at
    their operation adapters, so this transport layer only resolves and calls
    the public method.
    """
    func = getattr(self, method, None)
    if func is None or method.startswith("_"):
        raise Exception(f'method "{method}" is not supported')
    return func(*params)
