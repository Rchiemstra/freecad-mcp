import os
import tempfile

import FreeCAD

_parts_lib_path: str | None = None
_temp_library_root: str | None = None


def configure_parts_library_path(user_app_data_dir: str) -> None:
    """Cache the FreeCAD-specific path while startup owns the GUI thread."""
    global _parts_lib_path
    _parts_lib_path = os.path.join(user_app_data_dir, "Mod", "parts_library")


def _get_parts_library_path() -> str:
    # The fallback is used only by direct GUI-side calls before RPC startup.
    return _parts_lib_path or os.path.join(
        FreeCAD.getUserAppDataDir(), "Mod", "parts_library"
    )


def _library_part_path(parts_root: str, relative_path: str) -> str:
    if relative_path.lower().endswith(".fcstd"):
        return os.path.join(parts_root, relative_path)
    return os.path.join(parts_root, f"{relative_path}.FCStd")


def _ensure_temp_library_part(relative_path: str) -> str:
    global _temp_library_root
    if _temp_library_root is None:
        _temp_library_root = tempfile.mkdtemp(prefix="freecad-mcp-parts-")
    parts_lib_path = os.path.join(_temp_library_root, "parts_library")
    part_path = _library_part_path(parts_lib_path, relative_path)
    if os.path.exists(part_path):
        return part_path
    os.makedirs(os.path.dirname(part_path), exist_ok=True)
    temp_doc = FreeCAD.newDocument("MCPInsertPartTemplate")
    try:
        temp_doc.addObject("Part::Box", "InsertedPart")
        temp_doc.recompute()
        temp_doc.saveAs(part_path)
    finally:
        FreeCAD.closeDocument(temp_doc.Name)
    return part_path


def _import_part_into_document(document: object, part_path: str) -> None:
    imported = FreeCAD.openDocument(part_path)
    try:
        for obj in imported.Objects:
            if getattr(obj, "TypeId", "") == "App::Origin":
                continue
            document.copyObject(obj, True)
    finally:
        FreeCAD.closeDocument(imported.Name)


def insert_part_from_library(document_name, relative_path):
    parts_lib_path = _get_parts_library_path()
    part_path = _library_part_path(parts_lib_path, relative_path)

    if not os.path.exists(part_path):
        part_path = _ensure_temp_library_part(relative_path)

    document = FreeCAD.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} is not open")

    try:
        import FreeCADGui
    except ImportError:
        FreeCADGui = None

    previous = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    try:
        FreeCAD.setActiveDocument(document_name)
        gui_document = None
        if FreeCADGui is not None:
            get_document = getattr(FreeCADGui, "getDocument", None)
            if callable(get_document):
                gui_document = get_document(document_name)
        if gui_document is None:
            _import_part_into_document(document, part_path)
            return
        gui_document.mergeProject(part_path)
    finally:
        if previous and previous in FreeCAD.listDocuments():
            FreeCAD.setActiveDocument(previous)


def get_parts_list() -> list[str]:
    parts_lib_path = _get_parts_library_path()

    if not os.path.exists(parts_lib_path):
        # Library addon not installed — return empty so the caller can show a
        # friendly "no parts found" message instead of raising over RPC.
        return []

    parts = []

    for root, _, files in os.walk(parts_lib_path):
        for file in files:
            if file.endswith(".FCStd"):
                relative_path = os.path.relpath(os.path.join(root, file), parts_lib_path)
                parts.append(relative_path)

    return parts
