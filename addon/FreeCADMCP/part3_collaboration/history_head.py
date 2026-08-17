"""Undo/redo history-head capture and comparison for ADR §3.2."""

from __future__ import annotations

from typing import Any


def capture_undo_head(document: Any) -> dict[str, int | str]:
    names = list(getattr(document, "UndoNames", None) or [])
    count = int(getattr(document, "UndoCount", 0) or 0)
    head = str(names[0]) if names else ""
    return {"undo_count": count, "undo_head": head}


def capture_redo_head(document: Any) -> dict[str, int | str]:
    names = list(getattr(document, "RedoNames", None) or [])
    count = int(getattr(document, "RedoCount", 0) or 0)
    head = str(names[0]) if names else ""
    return {"redo_count": count, "redo_head": head}


def undo_head_matches(
    document: Any,
    expected_undo_count: int,
    expected_undo_head: str,
) -> bool:
    live = capture_undo_head(document)
    return (
        live["undo_count"] == int(expected_undo_count)
        and live["undo_head"] == str(expected_undo_head)
    )


def redo_head_matches(
    document: Any,
    expected_redo_count: int,
    expected_redo_head: str,
) -> bool:
    live = capture_redo_head(document)
    return (
        live["redo_count"] == int(expected_redo_count)
        and live["redo_head"] == str(expected_redo_head)
    )


__all__ = [
    "capture_redo_head",
    "capture_undo_head",
    "redo_head_matches",
    "undo_head_matches",
]
