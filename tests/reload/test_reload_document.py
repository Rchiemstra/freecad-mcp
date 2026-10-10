"""Unit coverage for the typed ``reload_document`` lifecycle slice."""

from __future__ import annotations

import zipfile

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.reload_document import run_reload_document
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def test_reload_document_verifies_without_native_mutation():
    events: list[str] = []
    document = FakeDocument(events)
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert "commit" not in events
    assert api.getDocument("Doc") is not None


def test_missing_document_is_rejected():
    events: list[str] = []
    collab, _api = collaborators(None, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def test_a_document_with_unsaved_changes_is_not_reloaded():
    """reload_document reported success and silently threw the edits away."""

    events: list[str] = []
    document = FakeDocument(events)
    document.hasPendingFileChanges = lambda: True
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HAS_UNSAVED_CHANGES"
    assert "save_document" in result["error"]
    assert api.getDocument("Doc") is document


def test_a_reload_reports_the_name_it_was_reopened_under():
    """Reopening names the document after its file; the caller must learn it."""

    events: list[str] = []
    document = FakeDocument(events)
    document.FileName = "/tmp/stress_sk.FCStd"
    document.hasPendingFileChanges = lambda: False
    collab, _api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is True
    assert result["document_name"] == "stress_sk"
    assert result["previous_name"] == "Doc"


def test_malformed_document_xml_is_rejected_before_the_document_is_closed(tmp_path):
    """A broken Document.xml must fail the reload and leave the open document."""

    events: list[str] = []
    document = FakeDocument(events)
    path = tmp_path / "broken.FCStd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Document.xml",
            '<Document><Float value="7.5"42.0000000000000000"/></Document>',
        )
    document.FileName = str(path)
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["error_code"] == "RELOAD_DOCUMENT_FAILED"
    assert "Document.xml" in result["error"]
    assert api.getDocument("Doc") is document


def _valid_fcstd(path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Document.xml", "<Document/>")


def test_a_valid_fcstd_still_reloads(tmp_path):
    """A real zip with well-formed Document.xml reloads and reports the new name."""

    events: list[str] = []
    document = FakeDocument(events)
    path = tmp_path / "kept.FCStd"
    _valid_fcstd(path)
    document.FileName = str(path)
    collab, _api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert result["document_name"] == "kept"
    assert result["previous_name"] == "Doc"


def test_a_non_zip_file_is_refused_before_the_document_is_closed(tmp_path):
    """Bytes that only start with a zip local header are not an FCStd."""

    events: list[str] = []
    document = FakeDocument(events)
    path = tmp_path / "not-a-valid.FCStd"
    path.write_bytes(b"PK\x03\x04not-a-valid-fcstd")
    document.FileName = str(path)
    collab, api = collaborators(document, events)

    result = run_reload_document(collab, "Doc")

    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["error_code"] == "RELOAD_DOCUMENT_FAILED"
    assert "not a FreeCAD document" in result["error"]
    assert api.getDocument("Doc") is document
