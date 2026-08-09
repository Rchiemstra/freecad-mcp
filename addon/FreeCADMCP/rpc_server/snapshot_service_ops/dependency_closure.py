"""Document dependency ordering and closure for snapshots."""

from __future__ import annotations

from contextlib import suppress
from typing import Any

from .link_helpers import is_link_property, reference_entries


def dependency_order(primary, documents: list[Any]) -> list[Any]:
    by_name = {doc.Name: doc for doc in documents}
    graph: dict[str, set[str]] = {}
    for doc in documents:
        try:
            graph[doc.Name] = {
                dep.Name for dep in doc.getDependentDocuments()
                if dep.Name in by_name and dep.Name != doc.Name
            }
        except Exception:
            graph[doc.Name] = set()
    ordered: list[str] = []
    visited: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in active:  # cycle: the active member will be appended by its caller
            return
        active.add(name)
        for dependency in sorted(graph.get(name, ())):
            visit(dependency)
        active.remove(name)
        visited.add(name)
        ordered.append(name)

    visit(primary.Name)
    for name in sorted(by_name):
        visit(name)
    # The primary must open last even when a cycle made it appear earlier.
    ordered = [name for name in ordered if name != primary.Name] + [primary.Name]
    return [by_name[name] for name in ordered]


def dependency_closure(primary) -> list[Any]:
    """Combine FreeCAD's dependency API with explicit link traversal for cycles."""
    by_name = {primary.Name: primary}
    pending = [primary]
    while pending:
        current = pending.pop()
        candidates = []
        with suppress(Exception):
            candidates.extend(current.getDependentDocuments())
        for obj in current.Objects:
            for prop in getattr(obj, "PropertiesList", []):
                try:
                    prop_type = obj.getTypeIdOfProperty(prop)
                    if not is_link_property(prop_type) and not (
                        getattr(obj, "TypeId", "") == "App::Link"
                        and prop == "LinkedObject"
                    ):
                        continue
                    value = getattr(obj, prop)
                except Exception:
                    continue
                candidates.extend(
                    target.Document for target, _subs in reference_entries(value)
                    if getattr(target, "Document", None) is not None
                )
        for candidate in candidates:
            if candidate.Name not in by_name:
                by_name[candidate.Name] = candidate
                pending.append(candidate)
    return list(by_name.values())
