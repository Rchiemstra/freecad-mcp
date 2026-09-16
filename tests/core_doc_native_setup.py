"""Fixtures for core document native qualification."""

from __future__ import annotations

import tempfile
from pathlib import Path


def temp_document_path(document, suffix: str = ".FCStd") -> str:
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    handle.close()
    path = Path(handle.name)
    document.saveAs(str(path))
    return str(path)


def prepare_core_document(document, kind: str) -> dict[str, object]:
    if kind == "empty":
        return {}
    if kind == "with_object":
        document.addObject("App::FeaturePython", "TypedBox")
        document.recompute()
        return {"object": "TypedBox"}
    if kind == "with_undo":
        marker = document.addObject("App::FeaturePython", "UndoMarker")
        marker.Label = "Initial"
        document.recompute()
        marker.Label = "Changed"
        document.recompute()
        undo = getattr(document, "undo", None)
        if callable(undo):
            undo()
        return {}
    if kind == "saved":
        path = temp_document_path(document)
        return {"path": path}
    raise KeyError(kind)
