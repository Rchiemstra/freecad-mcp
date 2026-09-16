from __future__ import annotations

# ruff: noqa: F403
from ._support import *

"""Thread-local mutation context for XML-RPC handlers."""

def call_with_mutation_context(self, func, params, context):
    from ..cad_methods_ops.cad_mutation import cad_mutation_rpc_method

    self._mutation_context.value = context
    try:
        with cad_mutation_rpc_method(context.get("method")):
            return func(*params)
    finally:
        if hasattr(self._mutation_context, "value"):
            del self._mutation_context.value
