"""Explicit recompute declarations for typed mutation RPC methods (ADR §5 / §11.7)."""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path


class RecomputePolicy(Enum):
    NONE = "none"
    TARGET = "target"

    @property
    def native_recompute_bool(self) -> bool:
        return self is RecomputePolicy.TARGET


# Typed mutations that defer coordinator-owned recompute at the RPC boundary.
# ADR §11.1: create/close document and repair_references are none.
_RECOMPUTE_NONE_METHODS = frozenset(
    {
        "create_document",
        "close_document",
        "repair_references",
    }
)


def _gateway_dispatch_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / "generated"
        / "capabilities"
        / "gateway_dispatch.json"
    )


@lru_cache(maxsize=1)
def mutation_rpc_methods() -> frozenset[str]:
    payload = json.loads(_gateway_dispatch_path().read_text(encoding="utf-8"))
    return frozenset(
        entry["rpc_method"]
        for entry in payload["entries"]
        if entry.get("mutation_class") == "mutation"
    )


def declared_policy(method: str) -> RecomputePolicy | None:
    if method not in mutation_rpc_methods():
        return None
    if method in _RECOMPUTE_NONE_METHODS:
        return RecomputePolicy.NONE
    return RecomputePolicy.TARGET


def assert_recompute_policy(method: str | None, native_recompute: bool) -> None:
    """Fail closed when a typed mutation disagrees with its registry declaration."""

    if not method:
        return
    policy = declared_policy(method)
    if policy is None:
        return
    expected = policy.native_recompute_bool
    if native_recompute != expected:
        raise RuntimeError(
            "run_cad_mutation native_recompute mismatch for "
            f"{method!r}: handed {native_recompute!r}, registry declares "
            f"{policy.value!r} ({expected=!r})"
        )


__all__ = [
    "RecomputePolicy",
    "assert_recompute_policy",
    "declared_policy",
    "mutation_rpc_methods",
]
