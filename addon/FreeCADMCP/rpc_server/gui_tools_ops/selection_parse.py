"""Selection parsing helpers for subshape selection."""

from __future__ import annotations

from typing import Any


def parse_selection_entry(item: Any) -> tuple[str, str, str | None]:
    """Return (object_name, sub_name, error_message)."""
    if isinstance(item, str):
        if ":" in item:
            obj_name, sub = item.split(":", 1)
            return obj_name.strip(), sub.strip(), None
        return item.strip(), "", None
    if isinstance(item, dict):
        obj_name = str(
            item.get("object")
            or item.get("obj")
            or item.get("name")
            or ""
        ).strip()
        sub = str(
            item.get("sub")
            or item.get("subshape")
            or item.get("subName")
            or ""
        ).strip()
        return obj_name, sub, None
    return "", "", f"Unsupported selection entry: {item!r}"
