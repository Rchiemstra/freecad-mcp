"""Server-side begin-time revision fence for checked-edit sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class CheckedEditFence:
    document_instance_id: int
    lifecycle_epoch: int
    revisions: tuple[dict[str, Any], ...]


_store: dict[str, CheckedEditFence] = {}
_lock = Lock()


def _normalize_revisions(
    revisions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for item in revisions:
        if not isinstance(item, Mapping):
            continue
        entry: dict[str, Any] = {}
        for key in ("kind", "subject", "property_name", "revision"):
            if key in item and item[key] is not None:
                entry[key] = item[key]
        if entry.get("kind"):
            normalized.append(entry)
    return tuple(normalized)


def store_begin_fence(
    session_id: str,
    *,
    document_instance_id: int,
    lifecycle_epoch: int,
    revisions: Sequence[Mapping[str, Any]],
) -> None:
    fence = CheckedEditFence(
        document_instance_id=int(document_instance_id),
        lifecycle_epoch=int(lifecycle_epoch),
        revisions=_normalize_revisions(revisions),
    )
    with _lock:
        _store[str(session_id)] = fence


def pop_begin_fence(session_id: str) -> CheckedEditFence | None:
    with _lock:
        return _store.pop(str(session_id), None)


def discard_begin_fence(session_id: str) -> None:
    with _lock:
        _store.pop(str(session_id), None)


def clear_begin_fences() -> None:
    with _lock:
        _store.clear()


__all__ = [
    "CheckedEditFence",
    "clear_begin_fences",
    "discard_begin_fence",
    "pop_begin_fence",
    "store_begin_fence",
]
