"""The RPC method being served, for code that runs on its behalf."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_ACTIVE_RPC_METHOD: ContextVar[str | None] = ContextVar(
    "freecad_mcp_cad_mutation_method", default=None
)


@contextmanager
def rpc_method_scope(method: str | None) -> Iterator[None]:
    """Mark *method* as the RPC being served until the block exits."""

    token = _ACTIVE_RPC_METHOD.set(method)
    try:
        yield
    finally:
        _ACTIVE_RPC_METHOD.reset(token)


def current_rpc_method() -> str | None:
    return _ACTIVE_RPC_METHOD.get()


__all__ = ["current_rpc_method", "rpc_method_scope"]
