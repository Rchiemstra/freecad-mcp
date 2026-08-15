"""Bounded readiness inspection for dispatcher-owned mutation admission."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from .mutation_readiness import document_readiness

_TRANSIENT_REASONS = frozenset(
    {
        "native_recomputing",
        "pending_recompute",
        "pending_object_removal",
        "collaboration_notifications_replaying",
        "native_not_ready",
    }
)
_ASYNCHRONOUS_TRANSIENT_REASONS = frozenset(
    {
        "native_recomputing",
        "collaboration_notifications_replaying",
    }
)
_IMMEDIATE_REJECTION_REASONS = frozenset(
    {
        "document_quarantined",
        "automation_paused",
        "collaboration_commit_poisoned",
        "native_transaction_in_progress",
    }
)


def blocking_readiness_reasons(
    item: dict[str, Any],
    *,
    allow_pending_recompute: bool = False,
) -> list[str]:
    """Return blockers after applying one operation's native recompute policy."""

    reasons = list(item.get("reasons") or ())
    if not allow_pending_recompute or not item.get("must_execute"):
        return reasons
    reasons = [reason for reason in reasons if reason != "pending_recompute"]
    # Native ``ready=false`` is normally authoritative.  For the explicit
    # deferred policy, however, the native readiness record is false solely
    # because mustExecute is true.  Remove that aggregate reason only when no
    # other native/local field can account for it.
    other_native_blocker = bool(
        item.get("pending_transaction")
        or item.get("booked_transaction_id") not in (None, 0)
        or item.get("transaction_locked")
        or item.get("recomputing")
        or item.get("pending_removal")
        or item.get("collaboration_blocked")
        or item.get("collaboration_poisoned")
    )
    if not other_native_blocker:
        reasons = [reason for reason in reasons if reason != "native_not_ready"]
    return reasons


def _checkpoint(inflight: Any, phase: str) -> None:
    token = getattr(inflight, "token", None)
    checkpoint = getattr(token, "checkpoint", None)
    if callable(checkpoint):
        checkpoint(phase)


def _settle_synchronously(
    documents: Sequence[Any],
    *,
    allow_pending_recompute: bool = False,
) -> None:
    """Settle explicit recompute and queued-removal work without a nested event loop.

    Queued collaboration/barrier states remain blocked for a later request;
    processing arbitrary Qt events between admission and commit would allow
    unrelated RPC/timer reentrancy at the transaction boundary.
    """

    for document in documents:
        readiness = document_readiness(document)
        if not readiness["recomputing"] and (
            readiness.get("pending_removal")
            or (not allow_pending_recompute and readiness["must_execute"])
        ):
            recompute = getattr(document, "recompute", None)
            if callable(recompute):
                recompute()


def _can_settle_synchronously(
    blocked: Sequence[dict[str, Any]],
    *,
    allow_pending_recompute: bool,
) -> bool:
    """Return whether one explicit recompute can make local progress.

    Native recomputing and notification replay require the GUI callback to
    yield and later resume.  This synchronous helper declines those states;
    the dispatcher-owned continuation retries them after an authoritative
    document event.
    """

    return bool(
        any(
            not item.get("recomputing")
            and (
                item.get("pending_removal")
                or (not allow_pending_recompute and item.get("must_execute"))
            )
            for item in blocked
        )
    )


def settle_pending_mutation_readiness(
    documents: Sequence[Any],
    *,
    inflight: Any = None,
    settle: Callable[[Sequence[Any]], None] | None = None,
    allow_pending_recompute: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    """Return readiness after at most one explicit synchronous recompute.

    ``True`` means a settle callback ran.  Pause, quarantine, poison, active
    transactions, native recomputing, and notification replay are never waited
    through.  The dispatcher-owned continuation handles the latter two before
    the GUI task is marked running.
    """

    initial = [document_readiness(document) for document in documents]
    blocked = [
        item
        for item in initial
        if blocking_readiness_reasons(
            item, allow_pending_recompute=allow_pending_recompute
        )
    ]
    if not blocked:
        return initial, False
    reasons = {
        reason
        for item in blocked
        for reason in blocking_readiness_reasons(
            item, allow_pending_recompute=allow_pending_recompute
        )
    }
    if reasons & _IMMEDIATE_REJECTION_REASONS or not reasons <= _TRANSIENT_REASONS:
        return initial, False
    if settle is None and not _can_settle_synchronously(
        blocked,
        allow_pending_recompute=allow_pending_recompute,
    ):
        return initial, False

    _checkpoint(inflight, "mutation_readiness_wait_before")
    if settle is not None:
        settle(documents)
    else:
        _settle_synchronously(
            documents, allow_pending_recompute=allow_pending_recompute
        )
    _checkpoint(inflight, "mutation_readiness_wait_after")
    return [document_readiness(document) for document in documents], True


def await_transient_mutation_readiness(
    documents: Sequence[Any],
    *,
    inflight: Any = None,
    settle: Callable[[Sequence[Any]], None] | None = None,
    allow_pending_recompute: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    """Inspect readiness at the dispatcher continuation boundary.

    Synchronously settleable ``mustExecute`` and pending-removal work retains
    the historical one-turn behavior. Recompute-in-progress and
    notification-replay states are returned unchanged so
    :class:`GuiDispatchCore` can defer the logical request until an
    authoritative document observer event fires.
    """

    return settle_pending_mutation_readiness(
        documents,
        inflight=inflight,
        settle=settle,
        allow_pending_recompute=allow_pending_recompute,
    )


def asynchronous_transient_document_keys(
    readiness: Sequence[dict[str, Any]],
    *,
    allow_pending_recompute: bool = True,
) -> tuple[str, ...]:
    """Return documents whose only concrete blockers need an event-loop turn."""

    keys: list[str] = []
    allowed = _ASYNCHRONOUS_TRANSIENT_REASONS | {
        "native_not_ready",
        "pending_object_removal",
    }
    for item in readiness:
        reasons = set(
            blocking_readiness_reasons(
                item,
                allow_pending_recompute=allow_pending_recompute,
            )
        )
        if (
            reasons & _ASYNCHRONOUS_TRANSIENT_REASONS
            and reasons <= allowed
        ):
            name = str(item.get("document") or "")
            if name and name not in keys:
                keys.append(name)
    return tuple(keys)


__all__ = [
    "asynchronous_transient_document_keys",
    "await_transient_mutation_readiness",
    "blocking_readiness_reasons",
    "settle_pending_mutation_readiness",
]
