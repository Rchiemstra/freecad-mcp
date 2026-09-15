"""Native qualification matrix for typed ``spreadsheet_get_cells``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import collaborators, load_runner, require_native_collaboration

pytestmark = pytest.mark.core


def _prepare(document):
    if document.getObject("Target") is None:
        try:
            document.addObject("Spreadsheet::Sheet", "Target")
        except Exception:
            document.addObject("App::FeaturePython", "Target")
    document.recompute()
    return {"sheet": "Target"}


def test_spreadsheet_get_cells_native_success_observes():
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("spreadsheet_get_cells")
    document = FreeCAD.newDocument("MCPSpreadsheetGetCellsNativeObserved")
    doc_name = document.Name
    try:
        _prepare(document)
        result = runner(collaborators(FreeCAD, lambda _d: None), doc_name, "Target", ["A1"])
        assert result["success"] is True
        assert result["outcome"] == "observed"
        assert result["sheet"] == "Target"
        assert isinstance(result["cells"], list)
        assert result["cells"]
    finally:
        FreeCAD.closeDocument(doc_name)


def test_spreadsheet_get_cells_native_missing_document_keeps_typed_error():
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("spreadsheet_get_cells")
    result = runner(collaborators(FreeCAD, lambda _d: None), "MissingNativeDoc", "Target", ["A1"])
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
