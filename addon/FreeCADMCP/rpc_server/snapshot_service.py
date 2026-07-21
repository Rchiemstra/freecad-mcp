"""GUI-thread FCStd snapshots for isolated read-only workers."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

import FreeCAD
import FreeCADGui

from .worker_protocol import ProtocolError, validate_subelement_reference


_SAFE_DOCUMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_link_property(prop_type: str) -> bool:
    """Recognize current document and cross-document link property aliases."""
    return "PropertyLink" in prop_type or "PropertyXLink" in prop_type


def _selection_state() -> list[tuple[str, str, tuple[str, ...]]]:
    try:
        return [
            (
                item.DocumentName,
                item.ObjectName,
                tuple(str(name) for name in getattr(item, "SubElementNames", [])),
            )
            for item in FreeCADGui.Selection.getSelectionEx()
        ]
    except Exception:
        return []


def _document_state(doc) -> dict[str, Any]:
    dependencies = []
    try:
        dependencies = sorted(item.Name for item in doc.getDependentDocuments())
    except Exception:
        pass
    return {
        "document_name": doc.Name,
        "document_label": getattr(doc, "Label", doc.Name),
        "document_uid": str(getattr(doc, "Uid", "")),
        "document_id": str(getattr(doc, "Id", "")),
        "original_filename": getattr(doc, "FileName", ""),
        "modified": bool(getattr(doc, "Modified", False)),
        "object_count": len(getattr(doc, "Objects", [])),
        "dependencies": dependencies,
        "has_pending_transaction": bool(getattr(doc, "HasPendingTransaction", False)),
        "transacting": bool(getattr(doc, "Transacting", False)),
        "last_modified_date": str(getattr(doc, "LastModifiedDate", "")),
    }


def _reference_entries(value) -> list[tuple[Any, list[str]]]:
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value and hasattr(value[0], "Document"):
        subs: list[str] = []
        for item in value[1:]:
            if isinstance(item, str):
                subs.append(item)
            elif isinstance(item, (list, tuple)):
                subs.extend(str(sub) for sub in item)
        return [(value[0], subs)]
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            result.extend(_reference_entries(item))
        return result
    return []


def _collect_link_manifest(
    documents: list[Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    links: list[dict[str, Any]] = []
    broken: list[str] = []
    invalid_subelements: list[str] = []
    open_names = set(FreeCAD.listDocuments().keys())
    for doc in documents:
        for obj in doc.Objects:
            for prop in getattr(obj, "PropertiesList", []):
                try:
                    prop_type = obj.getTypeIdOfProperty(prop)
                except Exception:
                    continue
                if not _is_link_property(prop_type) and not (
                    getattr(obj, "TypeId", "") == "App::Link" and prop == "LinkedObject"
                ):
                    continue
                try:
                    value = getattr(obj, prop)
                except Exception:
                    continue
                refs = _reference_entries(value)
                if (
                    getattr(obj, "TypeId", "") == "App::Link"
                    and prop == "LinkedObject"
                    and not refs
                ):
                    broken.append(f"{doc.Name}.{obj.Name}.{prop}")
                for target, subelements in refs:
                    target_doc = getattr(getattr(target, "Document", None), "Name", None)
                    target_name = getattr(target, "Name", None)
                    if (
                        not target_doc
                        or target_doc not in open_names
                        or not target_name
                        or FreeCAD.getDocument(target_doc).getObject(target_name) is None
                    ):
                        broken.append(f"{doc.Name}.{obj.Name}.{prop}")
                        continue
                    for subelement in subelements:
                        try:
                            validate_subelement_reference(target, subelement)
                        except ProtocolError:
                            invalid_subelements.append(
                                f"{target_doc}.{target_name}.{subelement}"
                            )
                    links.append({
                        "owner_document": doc.Name,
                        "owner_object": obj.Name,
                        "property": prop,
                        "property_type": prop_type,
                        "target_document": target_doc,
                        "target_object": target_name,
                        "subelements": subelements,
                    })
    return (
        links,
        sorted(set(broken)),
        sorted(set(invalid_subelements)),
    )


def _dependency_order(primary, documents: list[Any]) -> list[Any]:
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


def _dependency_closure(primary) -> list[Any]:
    """Combine FreeCAD's dependency API with explicit link traversal for cycles."""
    by_name = {primary.Name: primary}
    pending = [primary]
    while pending:
        current = pending.pop()
        candidates = []
        try:
            candidates.extend(current.getDependentDocuments())
        except Exception:
            pass
        for obj in current.Objects:
            for prop in getattr(obj, "PropertiesList", []):
                try:
                    prop_type = obj.getTypeIdOfProperty(prop)
                    if not _is_link_property(prop_type) and not (
                        getattr(obj, "TypeId", "") == "App::Link"
                        and prop == "LinkedObject"
                    ):
                        continue
                    value = getattr(obj, prop)
                except Exception:
                    continue
                candidates.extend(
                    target.Document for target, _subs in _reference_entries(value)
                    if getattr(target, "Document", None) is not None
                )
        for candidate in candidates:
            if candidate.Name not in by_name:
                by_name[candidate.Name] = candidate
                pending.append(candidate)
    return list(by_name.values())


def create_snapshot_bundle_gui(
    document_name: str | None,
    workspace: str,
    link_policy: str = "strict",
) -> dict[str, Any]:
    """Save a primary document and its open dependency closure on the GUI thread.

    ``link_policy``:
    - ``strict`` (default): fail on broken links / invalid subelements.
    - ``warn``: continue, omit bad refs from ``expected_links``, and return
      ``link_warnings`` so the worker can still run read-only analysis.
    """
    if link_policy not in {"strict", "warn"}:
        return {
            "ok": False,
            "error_code": "invalid_link_policy",
            "error": f"Unsupported link_policy: {link_policy!r}",
        }
    doc = FreeCAD.getDocument(document_name) if document_name else FreeCAD.ActiveDocument
    if doc is None:
        return {"ok": False, "error_code": "snapshot_failed", "error": "Document not found"}
    closure = _dependency_closure(doc)
    documents = _dependency_order(doc, closure)
    for dependency in documents:
        if not _SAFE_DOCUMENT_NAME.fullmatch(dependency.Name):
            return {
                "ok": False,
                "error_code": "snapshot_invalid_document_name",
                "error": f"Unsafe internal document name: {dependency.Name!r}",
            }
    links, broken, invalid_subelements = _collect_link_manifest(documents)
    link_warnings: list[str] = []
    if broken or invalid_subelements:
        if link_policy == "strict":
            if broken:
                return {
                    "ok": False,
                    "error_code": "external_link_unresolved",
                    "error": "Broken or unopened links: " + ", ".join(broken),
                }
            return {
                "ok": False,
                "error_code": "external_subelement_unresolved",
                "error": "Nonexistent linked subelements: " + ", ".join(invalid_subelements),
            }
        for item in broken:
            link_warnings.append(f"broken_link:{item}")
        for item in invalid_subelements:
            link_warnings.append(f"invalid_subelement:{item}")
        invalid_set = set(invalid_subelements)
        filtered_links = []
        for link in links:
            subs = list(link.get("subelements") or [])
            kept = [
                sub
                for sub in subs
                if f"{link['target_document']}.{link['target_object']}.{sub}"
                not in invalid_set
            ]
            if subs and not kept:
                # Entire LinkSub was invalid — omit from expected_links.
                continue
            entry = dict(link)
            entry["subelements"] = kept
            filtered_links.append(entry)
        links = filtered_links

    root = Path(workspace)
    snapshots = root / "snapshots"
    load = root / "load"
    shutil.rmtree(snapshots, ignore_errors=True)
    shutil.rmtree(load, ignore_errors=True)
    snapshots.mkdir(parents=True, exist_ok=True)
    load.mkdir(parents=True, exist_ok=True)

    active_before = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    selection_before = _selection_state()
    states_before = {item.Name: _document_state(item) for item in documents}
    started = time.monotonic()
    try:
        entries = []
        for index, item in enumerate(documents, 1):
            canonical = snapshots / f"{index:04d}_{item.Name}.FCStd"
            load_path = load / f"{item.Name}.FCStd"
            item.saveCopy(str(canonical))
            entries.append({
                **states_before[item.Name],
                "snapshot_filename": canonical.name,
                "snapshot_path": str(canonical),
                "load_filename": load_path.name,
                "load_path": str(load_path),
                "primary": item.Name == doc.Name,
            })
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "snapshot_failed",
            "error": f"Failed to save snapshot: {exc}",
        }
    duration_ms = (time.monotonic() - started) * 1000.0
    states_after = {item.Name: _document_state(item) for item in documents}
    active_after = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    selection_after = _selection_state()

    invariant_keys = (
        "document_name", "document_uid", "original_filename", "modified",
        "object_count", "dependencies", "has_pending_transaction", "transacting",
    )
    changed = any(
        states_before[name].get(key) != states_after[name].get(key)
        for name in states_before
        for key in invariant_keys
    )
    changed = changed or active_before != active_after or selection_before != selection_after
    if changed:
        shutil.rmtree(snapshots, ignore_errors=True)
        return {
            "ok": False,
            "error_code": "snapshot_state_changed",
            "error": "Document state changed while creating the snapshot",
        }

    result = {
        "ok": True,
        "primary_document": doc.Name,
        "snapshot_duration_ms": duration_ms,
        "active_document": active_before,
        "selection": selection_before,
        "documents": entries,
        "expected_links": links,
        "link_policy": link_policy,
        "state_indicators_best_effort": True,
    }
    if link_warnings:
        result["link_warnings"] = link_warnings
    return result


def create_primary_snapshot_gui(
    document_name: str | None,
    workspace: str,
    link_policy: str = "strict",
) -> dict[str, Any]:
    """Compatibility name retained while Phase 3 now includes dependencies."""
    return create_snapshot_bundle_gui(document_name, workspace, link_policy=link_policy)


def materialize_load_aliases(snapshot: dict[str, Any]) -> None:
    """Create exact-name aliases outside the GUI thread for document identity."""
    for entry in snapshot["documents"]:
        source = Path(entry["snapshot_path"])
        target = Path(entry["load_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, target)
        except OSError:
            import shutil

            shutil.copy2(source, target)
