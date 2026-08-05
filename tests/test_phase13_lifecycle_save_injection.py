"""Phase 18 contracts for FreeCAD-owned native persistence."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods import native_lifecycle_methods

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE = (
    ROOT
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "methods"
    / "native_lifecycle_methods.py"
)


class _Document:
    Name = "Model"
    FileName = "/work/Model.FCStd"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def save(self):
        self.calls.append(("save", self.FileName))
        return True

    def saveAsWithPolicy(self, destination, overwrite=False):
        if str(destination).endswith("Existing.FCStd") and not overwrite:
            return {"success": False, "status": "destination_exists"}
        self.FileName = str(destination)
        self.calls.append(("save_as", self.FileName))
        return {"success": True, "status": "saved"}


def _facade(document: _Document | None):
    freecad = SimpleNamespace(
        getDocument=lambda name: document if document and name == document.Name else None,
        listDocuments=lambda: ({document.Name: document} if document else {}),
    )
    return SimpleNamespace(
        _execution_collaborators=SimpleNamespace(freecad=freecad),
        _dispatch_gui=lambda callback: callback(),
    )


def test_native_lifecycle_module_has_no_python_document_authority() -> None:
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MODULE))

    forbidden = {
        "document_lease",
        "document_lock",
        "core_authority",
        "sidecar",
        "credential",
        "baseline",
        "recovery",
    }
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(marker in name for marker in forbidden for name in imports)


def test_save_and_finalize_delegate_only_to_native_freecad() -> None:
    document = _Document()
    facade = _facade(document)

    saved = native_lifecycle_methods.save_document(
        facade, {"document_name": "Model"}
    )
    finalized = native_lifecycle_methods.finalize_document_edit(
        facade,
        {"document_name": "Model"},
        save_mode="save_as",
        destination="/work/Final.FCStd",
        overwrite=True,
    )

    assert saved == {
        "success": True,
        "saved": True,
        "document_name": "Model",
        "canonical_path": "/work/Model.FCStd",
        "authority": "native_freecad",
    }
    assert finalized["success"] is True
    assert finalized["finalized"] is True
    assert finalized["release"] == {
        "authority": "native_freecad",
        "lease_present": False,
    }
    assert document.calls == [
        ("save", "/work/Model.FCStd"),
        ("save_as", "/work/Final.FCStd"),
    ]


def test_native_lifecycle_rejects_missing_document_and_invalid_mode() -> None:
    missing = native_lifecycle_methods.save_document(
        _facade(None), {"document_name": "Missing"}
    )
    invalid = native_lifecycle_methods.finalize_document_edit(
        _facade(_Document()),
        {"document_name": "Model"},
        save_mode="recover",
    )

    assert missing["error_code"] == "DOCUMENT_NOT_FOUND"
    assert invalid["error_code"] == "INVALID_SAVE_MODE"


def test_save_as_never_silently_ignores_legacy_safety_options() -> None:
    facade = _facade(_Document())

    default_save_as = native_lifecycle_methods.save_document_as(
        facade,
        {"document_name": "Model"},
        "/work/New.FCStd",
        overwrite=False,
    )
    conflict = native_lifecycle_methods.save_document_as(
        facade,
        {"document_name": "Model"},
        "/work/Existing.FCStd",
        overwrite=False,
    )
    hashed = native_lifecycle_methods.save_document_as(
        facade,
        {"document_name": "Model"},
        "/work/Existing.FCStd",
        overwrite=True,
        expected_destination_sha256="abc",
    )
    profiled = native_lifecycle_methods.save_document(
        facade,
        {"document_name": "Model"},
        validation_profile="strict",
    )
    null_selector = native_lifecycle_methods.save_document(facade, None)

    assert default_save_as["success"] is True
    assert conflict["error_code"] == "DESTINATION_EXISTS"
    assert hashed["error_code"] == "EXPECTED_DESTINATION_HASH_UNSUPPORTED"
    assert profiled["error_code"] == "VALIDATION_PROFILE_UNSUPPORTED"
    assert null_selector["error_code"] == "DOCUMENT_NOT_FOUND"


def test_legacy_uuid_selector_is_explicitly_deprecated() -> None:
    document = _Document()
    result = native_lifecycle_methods.save_document(
        _facade(document),
        {"document_session_uuid": "session-1"},
    )

    assert result["error_code"] == "DOCUMENT_SESSION_SELECTOR_DEPRECATED"
    assert document.calls == []


def test_resolution_and_save_run_only_inside_gui_dispatch() -> None:
    state = {"inside_dispatch": False}
    document = _Document()

    def assert_dispatched(value):
        assert state["inside_dispatch"] is True
        return value

    freecad = SimpleNamespace(
        getDocument=lambda name: assert_dispatched(
            document if name == document.Name else None
        ),
        listDocuments=lambda: assert_dispatched({document.Name: document}),
    )

    def dispatch(callback):
        state["inside_dispatch"] = True
        try:
            return callback()
        finally:
            state["inside_dispatch"] = False

    facade = SimpleNamespace(
        _execution_collaborators=SimpleNamespace(freecad=freecad),
        _dispatch_gui=dispatch,
    )

    result = native_lifecycle_methods.save_document(
        facade, {"document_name": "Model"}
    )

    assert result["success"] is True
    assert state["inside_dispatch"] is False
