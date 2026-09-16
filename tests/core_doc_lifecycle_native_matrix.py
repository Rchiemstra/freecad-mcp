"""Shared native qualification matrix for lifecycle document ops."""

from __future__ import annotations

from tests.core_doc_native_matrix import collaborators, load_runner, require_native_collaboration
from tests.core_doc_native_setup import prepare_core_document


def check_create_document_success(_monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("create_document")
    doc_name = "MCPCreateDocumentNativeVerified"
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), doc_name)
        assert result["success"] is True
        assert result["outcome"] == "verified"
        assert result["document_name"] == doc_name
        assert doc_name in FreeCAD.listDocuments()
    finally:
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_create_document_validation_failure() -> None:
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner("create_document")
    doc_name = "MCPCreateDocumentNativeCompensated"
    original_verify = subject.verify_create_document

    def fail_verify(_app: object, _request: object) -> None:
        return None

    subject.verify_create_document = fail_verify
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), doc_name)
        assert result["success"] is False
        assert result["outcome"] == "compensated"
        assert doc_name not in FreeCAD.listDocuments()
    finally:
        subject.verify_create_document = original_verify
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_create_document_already_exists() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("create_document")
    existing = FreeCAD.newDocument("MCPExistingCreateDocument")
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), existing.Name)
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_ALREADY_EXISTS"
    finally:
        FreeCAD.closeDocument(existing.Name)


def check_open_document_success(_monkeypatch) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("open_document")
    fixture = FreeCAD.newDocument("MCPOpenDocumentFixture")
    opened_name: str | None = None
    try:
        ctx = prepare_core_document(fixture, "saved")
        path = ctx["path"]
        FreeCAD.closeDocument(fixture.Name)
        result = runner(collaborators(FreeCAD, lambda _d: None), path)
        assert result["success"] is True
        assert result["outcome"] == "verified"
        candidate = result.get("document_name")
        opened_name = candidate if isinstance(candidate, str) else None
        assert opened_name and opened_name in FreeCAD.listDocuments()
    finally:
        if opened_name and opened_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(opened_name)


def check_open_document_validation_failure() -> None:
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner("open_document")
    fixture = FreeCAD.newDocument("MCPOpenDocumentRollbackFixture")
    opened_name: str | None = None
    original_verify = subject.verify_open_document

    def fail_verify(_app: object, _request: object, _opened_name: str) -> None:
        return None

    subject.verify_open_document = fail_verify
    try:
        ctx = prepare_core_document(fixture, "saved")
        path = ctx["path"]
        FreeCAD.closeDocument(fixture.Name)
        result = runner(collaborators(FreeCAD, lambda _d: None), path)
        assert result["success"] is False
        assert result["outcome"] == "compensated"
        for name in FreeCAD.listDocuments():
            if name not in {fixture.Name}:
                opened_name = name
                break
        if opened_name:
            assert opened_name not in FreeCAD.listDocuments()
    finally:
        subject.verify_open_document = original_verify
        for name in list(FreeCAD.listDocuments()):
            try:
                FreeCAD.closeDocument(name)
            except Exception:
                pass


def check_open_document_missing_path() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("open_document")
    result = runner(
        collaborators(FreeCAD, lambda _d: None),
        "/no/such/document.FCStd",
    )
    assert result["success"] is False
    assert result["error_code"] == "OPEN_DOCUMENT_FAILED"


def check_close_document_success() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("close_document")
    document = FreeCAD.newDocument("MCPCloseDocumentNative")
    doc_name = document.Name
    result = runner(collaborators(FreeCAD, lambda _d: None), doc_name)
    assert result["success"] is True
    assert result["outcome"] == "verified"
    assert doc_name not in FreeCAD.listDocuments()


def check_close_document_missing() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("close_document")
    result = runner(collaborators(FreeCAD, lambda _d: None), "MissingNativeDoc")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def check_reload_document_success() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("reload_document")
    document = FreeCAD.newDocument("MCPReloadDocumentNative")
    prepare_core_document(document, "saved")
    doc_name = document.Name
    reopened_name: str | None = None
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), doc_name)
        assert result["success"] is True
        assert result["outcome"] == "verified"
        reopened_name = result["document_name"]
        assert isinstance(reopened_name, str)
        assert reopened_name in FreeCAD.listDocuments()
    finally:
        if reopened_name and reopened_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(reopened_name)
        if doc_name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(doc_name)


def check_reload_document_missing() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("reload_document")
    result = runner(collaborators(FreeCAD, lambda _d: None), "MissingNativeDoc")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"


def check_activate_document_success() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("activate_document")
    first = FreeCAD.newDocument("MCPActivateFirst")
    second = FreeCAD.newDocument("MCPActivateSecond")
    try:
        result = runner(collaborators(FreeCAD, lambda _d: None), second.Name)
        assert result["success"] is True
        assert result["outcome"] == "verified"
        assert FreeCAD.ActiveDocument.Name == second.Name
    finally:
        for name in (first.Name, second.Name):
            if name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(name)


def check_activate_document_missing() -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner("activate_document")
    result = runner(collaborators(FreeCAD, lambda _d: None), "MissingNativeDoc")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
