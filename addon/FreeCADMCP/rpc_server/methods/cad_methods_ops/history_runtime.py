"""Shared runtime helpers for undo/redo history operations."""

from __future__ import annotations

from .policy_runtime import lookup_document


def perform_history_action(document: object, action_name: str) -> None:
    action = getattr(document, action_name, None)
    if not callable(action):
        raise RuntimeError(f"document cannot {action_name}")
    action()


def history_stack_count(document: object, count_attr: str) -> int | None:
    value = getattr(document, count_attr, None)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def verify_history_stack(document: object, *, action_name: str, count_attr: str) -> str | None:
    action = getattr(document, action_name, None)
    if not callable(action):
        return "INVALID_DOCUMENT"
    count = history_stack_count(document, count_attr)
    if count is not None and count <= 0:
        return "EMPTY_HISTORY_STACK"
    return None


def admit_history_document(app: object, doc_name: str) -> object | None:
    return lookup_document(app, doc_name)


__all__ = [
    "admit_history_document",
    "perform_history_action",
    "verify_history_stack",
]
