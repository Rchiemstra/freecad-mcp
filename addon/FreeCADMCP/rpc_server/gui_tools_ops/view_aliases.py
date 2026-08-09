"""View-name normalization helpers for GUI tools."""

from __future__ import annotations

from .view_helpers import active_view

_VIEW_ALIASES = {
    "Rear": "Back",
    "Side": "Right",
    "SideRight": "Right",
    "SideLeft": "Left",
}


def normalize_view_name(view_name: str) -> str:
    name = str(view_name or "").strip()
    return _VIEW_ALIASES.get(name, name)


__all__ = ["active_view", "normalize_view_name"]
