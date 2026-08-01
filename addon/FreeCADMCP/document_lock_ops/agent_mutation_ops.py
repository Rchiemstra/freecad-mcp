from __future__ import annotations

import contextlib
import threading
from typing import Any

from .agent_mutation_state import _AgentMutationState

_agent_mutation_ctx = threading.local()


def _mutation_state(*, create: bool = False) -> _AgentMutationState | None:
    state = getattr(_agent_mutation_ctx, "state", None)
    if state is None and create:
        state = _AgentMutationState()
        _agent_mutation_ctx.state = state
    return state


def _normalized_mutation_keys(document_keys) -> frozenset[str]:
    if isinstance(document_keys, str):
        document_keys = (document_keys,)
    try:
        normalized_values = set()
        for value in document_keys:
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                normalized_values.add(normalized)
        normalized = frozenset(normalized_values)
    except TypeError as exc:
        raise ValueError("document mutation scope must be iterable") from exc
    if not normalized:
        raise ValueError("document mutation scope must not be empty")
    return normalized


def begin_agent_mutation_scope(request_id: str, document_keys) -> bool:
    """Begin an exact, request-scoped GUI mutation attribution context.

    Safe nesting is allowed only for the same non-empty request ID and the
    same exact set of declared document keys.  A different request, a changed
    scope, or mixing this API with the legacy marker poisons attribution until
    the outermost scope exits, so observers fail closed instead of accepting a
    re-entrant or undeclared mutation.
    """

    normalized_request_id = str(request_id or "").strip()
    if not normalized_request_id:
        raise ValueError("agent mutation request_id must not be empty")
    normalized_keys = _normalized_mutation_keys(document_keys)
    state = _mutation_state(create=True)
    assert state is not None
    if state.legacy_counts:
        state.violation = "request-scoped mutation nested inside legacy attribution"
    if state.depth == 0:
        state.request_id = normalized_request_id
        state.document_keys = normalized_keys
        state.violation = state.violation or ""
    elif (
        state.request_id != normalized_request_id
        or state.document_keys != normalized_keys
    ):
        state.violation = "nested mutation request or document scope mismatch"
    state.depth += 1
    return not state.violation


def end_agent_mutation_scope(request_id: str, document_keys) -> bool:
    """End one reference to an exact GUI mutation scope.

    Mismatched teardown is itself fail-closed.  It does not expose a still
    active outer request as valid attribution, but the state is cleared when
    the outermost reference has unwound so a bad request cannot poison later
    independent GUI work.
    """

    normalized_request_id = str(request_id or "").strip()
    normalized_keys = _normalized_mutation_keys(document_keys)
    state = _mutation_state()
    if state is None or state.depth <= 0:
        return False
    if (
        state.request_id != normalized_request_id
        or state.document_keys != normalized_keys
    ):
        state.violation = "mutation scope teardown mismatch"
    state.depth -= 1
    valid = not state.violation
    if state.depth == 0:
        state.request_id = ""
        state.document_keys = frozenset()
        state.violation = ""
        if not state.legacy_counts:
            with contextlib.suppress(AttributeError):
                delattr(_agent_mutation_ctx, "state")
    return valid


def get_agent_mutation_context() -> dict[str, Any]:
    """Return a token-free snapshot of the current thread's attribution."""

    state = _mutation_state()
    if state is None:
        return {
            "active": False,
            "request_id": None,
            "document_keys": (),
            "depth": 0,
            "valid": False,
            "violation": None,
            "thread_id": threading.get_ident(),
            "legacy": False,
        }
    strict_active = state.depth > 0
    legacy_active = bool(state.legacy_counts)
    return {
        "active": strict_active or legacy_active,
        "request_id": state.request_id if strict_active else None,
        "document_keys": tuple(
            sorted(
                state.document_keys
                if strict_active
                else state.legacy_counts.keys()
            )
        ),
        "depth": state.depth if strict_active else sum(state.legacy_counts.values()),
        "valid": bool(
            (strict_active and not state.violation and not legacy_active)
            or (legacy_active and not strict_active)
        ),
        "violation": state.violation or None,
        "thread_id": threading.get_ident(),
        "legacy": legacy_active and not strict_active,
    }
