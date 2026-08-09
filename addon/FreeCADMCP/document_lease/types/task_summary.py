from __future__ import annotations

import unicodedata

from .schema_constants import MAX_PERSISTED_TASK_SUMMARY_CHARS


def sanitize_persisted_task_summary(value: str | None) -> str:
    """Return a single-line, bounded sidecar-safe diagnostic summary.

    Task metadata can contain prompts, customer details, or terminal control
    characters.  Persistence is therefore opt-in and, even when enabled, uses
    a deliberately smaller representation than the in-memory/public-status
    value.  Unicode control/format/surrogate characters and all whitespace are
    normalized to ordinary spaces before the length cap is applied.
    """

    if not value:
        return ""
    characters: list[str] = []
    pending_space = False
    for character in str(value):
        if character.isspace() or unicodedata.category(character).startswith("C"):
            pending_space = bool(characters)
            continue
        if pending_space:
            if len(characters) >= MAX_PERSISTED_TASK_SUMMARY_CHARS:
                break
            characters.append(" ")
            pending_space = False
        if len(characters) >= MAX_PERSISTED_TASK_SUMMARY_CHARS:
            break
        characters.append(character)
    return "".join(characters).rstrip()
