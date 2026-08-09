"""Link property type and reference-entry helpers."""

from __future__ import annotations

from typing import Any


def is_link_property(prop_type: str) -> bool:
    return "PropertyLink" in prop_type or "PropertyXLink" in prop_type


def reference_entries(value: Any) -> list[tuple[Any, list[str]]]:
    """Return ordered ``(target, subelements)`` entries without reading shapes."""
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value:
        target = value[0]
        if hasattr(target, "Document") and hasattr(target, "Name"):
            subelements: list[str] = []
            for item in value[1:]:
                if isinstance(item, str):
                    if item:
                        subelements.append(item)
                elif isinstance(item, (list, tuple)):
                    subelements.extend(str(sub) for sub in item if str(sub))
            return [(target, subelements)]
    if isinstance(value, (list, tuple)):
        result: list[tuple[Any, list[str]]] = []
        for item in value:
            result.extend(reference_entries(item))
        return result
    return []


def property_type(obj: Any, property_name: str) -> str:
    for method_name in ("getTypeIdOfProperty", "getTypeOfProperty"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                return str(method(property_name))
            except Exception:
                pass
    return ""
