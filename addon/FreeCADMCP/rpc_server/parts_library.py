import os

import FreeCAD
import FreeCADGui


_parts_lib_path: str | None = None


def configure_parts_library_path(user_app_data_dir: str) -> None:
    """Cache the FreeCAD-specific path while startup owns the GUI thread."""
    global _parts_lib_path
    _parts_lib_path = os.path.join(user_app_data_dir, "Mod", "parts_library")


def _get_parts_library_path() -> str:
    # The fallback is used only by direct GUI-side calls before RPC startup.
    return _parts_lib_path or os.path.join(
        FreeCAD.getUserAppDataDir(), "Mod", "parts_library"
    )


def insert_part_from_library(document_name, relative_path):
    parts_lib_path = _get_parts_library_path()
    part_path = os.path.join(parts_lib_path, relative_path)

    if not os.path.exists(part_path):
        raise FileNotFoundError(f"Not found: {part_path}")

    document = FreeCAD.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} is not open")
    previous = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    try:
        FreeCAD.setActiveDocument(document_name)
        gui_document = FreeCADGui.getDocument(document_name)
        if gui_document is None:
            raise ValueError(f"GUI document {document_name!r} is unavailable")
        gui_document.mergeProject(part_path)
    finally:
        if previous and previous in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(previous)


def get_parts_list() -> list[str]:
    parts_lib_path = _get_parts_library_path()

    if not os.path.exists(parts_lib_path):
        # Library addon not installed — return empty so the caller can show a
        # friendly "no parts found" message instead of raising over XML-RPC.
        return []

    parts = []

    for root, _, files in os.walk(parts_lib_path):
        for file in files:
            if file.endswith(".FCStd"):
                relative_path = os.path.relpath(os.path.join(root, file), parts_lib_path)
                parts.append(relative_path)

    return parts
