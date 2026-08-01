"""Open snapshot documents and validate links for worker jobs."""

from __future__ import annotations

import FreeCAD

from .link_validation_post import (
    _attach_link_warnings,
    _validate_expected_links_post_recompute,
)
from .link_validation_pre import _validate_expected_links_pre_recompute


def open_snapshot_documents(snapshot: dict) -> tuple[list[str], object]:
    opened: list[str] = []
    for entry in snapshot["documents"]:
        doc = FreeCAD.openDocument(entry["load_path"])
        opened.append(doc.Name)
    primary_name = snapshot["primary_document"]
    primary = FreeCAD.getDocument(primary_name)
    if primary is None:
        raise RuntimeError(f"Primary snapshot did not open as {primary_name!r}")
    FreeCAD.setActiveDocument(primary.Name)
    return opened, primary


def validate_snapshot_links(snapshot: dict, result: dict) -> list[str]:
    if not (snapshot.get("expected_links") or snapshot.get("ignored_links")):
        return []
    link_anchors = _validate_expected_links_pre_recompute(snapshot)
    try:
        from ..worker_entry import _recompute_snapshot_documents
    except ImportError:
        from .link_validation_helpers import _recompute_snapshot_documents

    _recompute_snapshot_documents()
    link_validation_warnings = _validate_expected_links_post_recompute(link_anchors, snapshot)
    _attach_link_warnings(result, link_validation_warnings)
    return link_validation_warnings


def apply_recompute_option(primary, options: dict) -> None:
    recompute = options.get("recompute", "none")
    if recompute == "all":
        for doc in FreeCAD.listDocuments().values():
            doc.recompute()
    elif recompute == "target":
        primary.recompute()
