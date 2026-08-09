"""Link property recognition and reference normalization."""

from __future__ import annotations

from typing import Any


def is_link_property(prop_type: str) -> bool:
    """Recognize current document and cross-document link property aliases."""
    return "PropertyLink" in prop_type or "PropertyXLink" in prop_type


def reference_entries(value) -> list[tuple[Any, list[str]]]:
    """Normalize link values into targets and actual subelement names.

    FreeCAD serializes a whole-object ``PropertyLinkSub`` reference with an
    empty-string sentinel.  That sentinel is not a subelement and must not be
    sent through subelement existence validation.
    """
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value and hasattr(value[0], "Document"):
        subs: list[str] = []
        for item in value[1:]:
            if isinstance(item, str):
                if item:
                    subs.append(item)
            elif isinstance(item, (list, tuple)):
                subs.extend(str(sub) for sub in item if str(sub))
        return [(value[0], subs)]
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(reference_entries(item))
        return result
    return []
