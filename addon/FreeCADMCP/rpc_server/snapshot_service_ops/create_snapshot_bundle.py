"""GUI-thread snapshot bundle creation."""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import FreeCAD

from .dependency_closure import dependency_closure, dependency_order
from .document_state_helpers import document_state, selection_state
from .link_manifest import collect_link_manifest
from .link_policy import apply_link_policy

SAFE_DOCUMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

INVARIANT_KEYS = (
    "document_name", "document_uid", "original_filename", "modified",
    "object_count", "dependencies", "has_pending_transaction", "transacting",
)


def _validate_document_names(documents: list[Any]) -> dict[str, Any] | None:
    for dependency in documents:
        if not SAFE_DOCUMENT_NAME.fullmatch(dependency.Name):
            return {
                "ok": False,
                "error_code": "snapshot_invalid_document_name",
                "error": f"Unsafe internal document name: {dependency.Name!r}",
            }
    return None


def _snapshot_invariants_changed(
    states_before: dict[str, dict[str, Any]],
    states_after: dict[str, dict[str, Any]],
    *,
    active_before: str | None,
    active_after: str | None,
    selection_before: list[tuple[str, str, tuple[str, ...]]],
    selection_after: list[tuple[str, str, tuple[str, ...]]],
) -> bool:
    changed = any(
        states_before[name].get(key) != states_after[name].get(key)
        for name in states_before
        for key in INVARIANT_KEYS
    )
    return changed or active_before != active_after or selection_before != selection_after


def create_snapshot_bundle_gui(
    document_name: str | None,
    workspace: str,
    link_policy: str = "strict",
    mutation_generations: Mapping[str, int] | None = None,
    mutation_request_id: str = "",
    mutation_document_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Save a primary document and its open dependency closure on the GUI thread.

    ``link_policy``:
    - ``strict`` (default): fail on broken links / invalid subelements.
    - ``warn``: continue, omit bad refs from ``expected_links``, record structured
      ``ignored_links`` (owner, property, ``reference_index``, target, ignored
      subelements), and return ``link_warnings``. Phase-1/2 validation ignores only
      those indexed entries while strictly checking every retained manifest row.
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
    closure = dependency_closure(doc)
    documents = dependency_order(doc, closure)
    name_error = _validate_document_names(documents)
    if name_error is not None:
        return name_error

    links, broken, invalid_subelements = collect_link_manifest(documents)
    link_warnings: list[str] = []
    ignored_links: list[dict[str, Any]] = []
    if broken or invalid_subelements:
        policy_result = apply_link_policy(
            links, broken, invalid_subelements, link_policy=link_policy
        )
        if isinstance(policy_result, dict):
            return policy_result
        links, link_warnings, ignored_links = policy_result

    root = Path(workspace)
    snapshots = root / "snapshots"
    load = root / "load"
    shutil.rmtree(snapshots, ignore_errors=True)
    shutil.rmtree(load, ignore_errors=True)
    snapshots.mkdir(parents=True, exist_ok=True)
    load.mkdir(parents=True, exist_ok=True)

    active_before = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    selection_before = selection_state()
    states_before = {item.Name: document_state(item) for item in documents}
    started = time.monotonic()
    try:
        entries = []
        del mutation_generations, mutation_request_id, mutation_document_keys
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
    states_after = {item.Name: document_state(item) for item in documents}
    active_after = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    selection_after = selection_state()

    if _snapshot_invariants_changed(
        states_before,
        states_after,
        active_before=active_before,
        active_after=active_after,
        selection_before=selection_before,
        selection_after=selection_after,
    ):
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
        "ignored_links": ignored_links,
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
    mutation_generations: Mapping[str, int] | None = None,
    mutation_request_id: str = "",
    mutation_document_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Compatibility name retained while Phase 3 now includes dependencies."""
    return create_snapshot_bundle_gui(
        document_name,
        workspace,
        link_policy=link_policy,
        mutation_generations=mutation_generations,
        mutation_request_id=mutation_request_id,
        mutation_document_keys=mutation_document_keys,
    )
