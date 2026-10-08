"""Reload preflight delegated to FreeCAD's native document lifecycle."""

from __future__ import annotations

import os

import FreeCAD


def reload_preflight(self, doc_name: str):
    del self
    if doc_name not in FreeCAD.listDocuments():
        return f"Document '{doc_name}' is not loaded.", None, None
    try:
        doc = FreeCAD.getDocument(doc_name)
    except NameError:  # getDocument raises for unknown names
        doc = None
    file_path = doc.FileName
    if not file_path:
        return (
            f"Document '{doc_name}' has no file on disk "
            "(unsaved scratch document); nothing to reload from."
        ), None, None
    if not os.path.exists(file_path):
        return f"File for '{doc_name}' not found at {file_path!r}.", None, None
    return None, file_path, None
