from __future__ import annotations

# ruff: noqa: F403
from ._support import *

"""Thread-local mutation context for XML-RPC handlers."""

def call_with_mutation_context(self, func, params, context):
    self._mutation_context.value = context
    try:
        return func(*params)
    finally:
        if hasattr(self._mutation_context, "value"):
            del self._mutation_context.value
