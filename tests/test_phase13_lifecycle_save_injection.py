"""Phase 18 contracts for FreeCAD-owned native persistence."""

from __future__ import annotations

import ast
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods import native_lifecycle_methods
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import mutation_readiness

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
_REAL_STABLE_ARCHIVE_EVIDENCE = native_lifecycle_methods._stable_archive_evidence


def _fake_evidence(path: str, *, sha256: str = "a" * 64, mtime_ns: int = 7):
    return {
        "canonical_path": str(Path(path).resolve()),
        "size": 128,
        "mtime_ns": mtime_ns,
        "sha256": sha256,
        "file_identity": {"device": 1, "inode": 2},
        "archive": {
            "ok": True,
            "member_count": 2,
            "uncompressed_size": 64,
            "required_members": ["Document.xml"],
        },
    }


@pytest.fixture(autouse=True)
def _stable_evidence_without_host_files(monkeypatch):
    """Most unit doubles use synthetic /work paths; evidence itself is tested below."""

    monkeypatch.setattr(
        native_lifecycle_methods,
        "_stable_archive_evidence",
        lambda path: _fake_evidence(path),
    )


class _Document:
    Name = "Model"
    FileName = "/work/Model.FCStd"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.save_as_arguments: list[tuple[str, bool, str]] = []
        self.pending_file_changes = False
        self.last_save_failed = False
        self.durability_verified = True
        self.native_warnings: list[str] = []

    def hasPendingFileChanges(self):
        return self.pending_file_changes

    def lastCanonicalSaveFailed(self):
        return self.last_save_failed

    def save(self):
        self.calls.append(("save", self.FileName))
        return True

    def saveWithOutcome(self):
        self.calls.append(("save_outcome", self.FileName))
        return {
            "success": True,
            "save_disposition": "written",
            "file_written": True,
            "unchanged": False,
            "canonical_path": self.FileName,
            "resulting_clean": True,
            "durability_verified": self.durability_verified,
            "warnings": list(self.native_warnings),
            "message": f"Saved document changes to '{self.FileName}'.",
        }

    def saveAsWithPolicy(self, destination, overwrite=False):
        if str(destination).endswith("Existing.FCStd") and not overwrite:
            return {"success": False, "status": "destination_exists"}
        self.FileName = str(destination)
        self.calls.append(("save_as", self.FileName))
        return {"success": True, "status": "saved"}

    def saveAsWithOutcome(
        self,
        destination,
        overwrite=False,
        expected_destination_sha256="",
    ):
        self.save_as_arguments.append(
            (str(destination), bool(overwrite), str(expected_destination_sha256))
        )
        if str(destination).endswith("Existing.FCStd") and not overwrite:
            return {
                "success": False,
                "save_disposition": "failed",
                "error_code": "DESTINATION_EXISTS",
                "message": "Save As destination already exists",
                "canonical_path": self.FileName,
                "resulting_clean": False,
                "durability_verified": False,
                "warnings": [],
            }
        self.FileName = str(destination)
        self.calls.append(("save_as_outcome", self.FileName))
        return {
            "success": True,
            "save_disposition": "written",
            "file_written": True,
            "unchanged": False,
            "canonical_path": self.FileName,
            "resulting_clean": True,
            "durability_verified": self.durability_verified,
            "warnings": list(self.native_warnings),
            "message": f"Saved document changes to '{self.FileName}'.",
        }


class _OutcomeDocument(_Document):
    def saveWithOutcome(self):
        self.calls.append(("save_outcome", self.FileName))
        return {
            "success": True,
            "save_disposition": "unchanged",
            "file_written": False,
            "unchanged": True,
            "canonical_path": self.FileName,
            "resulting_clean": True,
            "durability_verified": False,
            "warnings": [],
            "message": "No document changes required persistence.",
        }


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
        "save_disposition": "written",
        "file_written": True,
        "unchanged": False,
        "canonical_path": "/work/Model.FCStd",
        "target_path": "/work/Model.FCStd",
        "resulting_clean": True,
        "reported_clean": True,
        "live_clean": True,
        "durability_verified": True,
        "warnings": [],
        "message": "Saved document changes to '/work/Model.FCStd'.",
        "authority": "native_freecad",
        "file_evidence": _fake_evidence("/work/Model.FCStd"),
    }
    assert finalized["success"] is True
    assert finalized["finalized"] is True
    assert finalized["release"] == {
        "authority": "native_freecad",
        "lease_present": False,
    }
    assert document.calls == [
        ("save_outcome", "/work/Model.FCStd"),
        ("save_as_outcome", "/work/Final.FCStd"),
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
    assert invalid["finalized"] is False
    assert invalid["released"] is False


@pytest.mark.parametrize(
    "outcome",
    [
        {
            "success": True,
            "save_disposition": "mystery",
            "file_written": False,
            "unchanged": False,
            "resulting_clean": True,
        },
        {
            "success": True,
            "save_disposition": "written",
            "file_written": False,
            "unchanged": False,
            "resulting_clean": True,
            "durability_verified": True,
        },
        {
            "success": True,
            "save_disposition": "unchanged",
            "file_written": True,
            "unchanged": True,
            "resulting_clean": True,
        },
        {
            "success": False,
            "save_disposition": "written",
            "file_written": True,
            "unchanged": False,
            "resulting_clean": True,
            "durability_verified": True,
        },
    ],
)
def test_contradictory_native_outcome_cannot_finalize_or_release(outcome) -> None:
    document = _Document()
    document.saveWithOutcome = lambda: dict(outcome)

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document), {"document_name": "Model"}
    )

    assert result["success"] is False
    assert result["saved"] is False
    assert result["error_code"] == "NATIVE_SAVE_OUTCOME_INCONSISTENT"
    assert result["finalized"] is False
    assert result["released"] is False


def test_every_save_failure_is_explicitly_not_finalized_or_released() -> None:
    result = native_lifecycle_methods.finalize_document_edit(
        _facade(None), {"document_name": "Missing"}
    )

    assert result["success"] is False
    assert result["finalized"] is False
    assert result["released"] is False


def test_save_as_never_silently_ignores_safety_options() -> None:
    document = _Document()
    facade = _facade(document)

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
        expected_destination_sha256="b" * 64,
    )
    profiled = native_lifecycle_methods.save_document(
        facade,
        {"document_name": "Model"},
        validation_profile="strict",
    )
    null_selector = native_lifecycle_methods.save_document(facade, None)

    assert default_save_as["success"] is True
    assert conflict["error_code"] == "DESTINATION_EXISTS"
    assert hashed["success"] is True
    assert document.save_as_arguments[-1] == (
        "/work/Existing.FCStd",
        True,
        "b" * 64,
    )
    assert profiled["error_code"] == "VALIDATION_PROFILE_UNSUPPORTED"
    assert null_selector["error_code"] == "DOCUMENT_NOT_FOUND"


def test_expected_hash_fails_closed_on_a_legacy_two_argument_runtime() -> None:
    class LegacySaveAsDocument(_Document):
        def saveAsWithOutcome(self, destination, overwrite=False):
            self.calls.append(("legacy_save_as_outcome", str(destination)))
            return super().saveAsWithOutcome(destination, overwrite)

    document = LegacySaveAsDocument()

    result = native_lifecycle_methods.save_document_as(
        _facade(document),
        {"document_name": "Model"},
        "/work/Existing.FCStd",
        overwrite=True,
        expected_destination_sha256="c" * 64,
    )

    assert result["success"] is False
    assert result["error_code"] == "EXPECTED_DESTINATION_HASH_UNSUPPORTED"
    assert document.calls == []
    assert document.save_as_arguments == []


def test_destination_hash_mismatch_cannot_finalize_or_release() -> None:
    document = _Document()

    def destination_changed(destination, overwrite, expected_destination_sha256):
        document.save_as_arguments.append(
            (str(destination), bool(overwrite), str(expected_destination_sha256))
        )
        return {
            "success": False,
            "save_disposition": "failed",
            "file_written": False,
            "unchanged": False,
            "canonical_path": document.FileName,
            "target_path": str(destination),
            "resulting_clean": False,
            "durability_verified": False,
            "warnings": [],
            "error_code": "DESTINATION_CHANGED",
            "message": "The Save As destination no longer matches its expected SHA-256.",
        }

    document.saveAsWithOutcome = destination_changed

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document),
        {"document_name": "Model"},
        save_mode="save_as",
        destination="/work/Existing.FCStd",
        overwrite=True,
        expected_destination_sha256="d" * 64,
    )

    assert result["success"] is False
    assert result["error_code"] == "DESTINATION_CHANGED"
    assert result["file_written"] is False
    assert result.get("finalized") is not True
    assert result.get("released") is not True
    assert document.save_as_arguments == [
        ("/work/Existing.FCStd", True, "d" * 64)
    ]


@pytest.mark.parametrize("native_failure", [False, True])
def test_unverified_written_outcome_cannot_finalize_or_release(
    native_failure: bool,
) -> None:
    document = _Document()
    document.durability_verified = False
    if native_failure:
        write_with_unverified_durability = document.saveAsWithOutcome

        def failed_after_install(
            destination,
            overwrite=False,
            expected_destination_sha256="",
        ):
            outcome = write_with_unverified_durability(
                destination,
                overwrite,
                expected_destination_sha256,
            )
            outcome.update(
                success=False,
                save_disposition="failed",
                error_code="TEST_INJECTED_DURABILITY_FAILURE",
                message="The destination changed, but directory durability is unverified.",
            )
            return outcome

        document.saveAsWithOutcome = failed_after_install

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document),
        {"document_name": "Model"},
        save_mode="save_as",
        destination="/work/Final.FCStd",
        overwrite=True,
    )

    assert result["success"] is False
    assert result["saved"] is False
    assert result["file_written"] is True
    assert result["durability_verified"] is False
    assert result["error_code"] == (
        "TEST_INJECTED_DURABILITY_FAILURE"
        if native_failure
        else "DURABILITY_UNVERIFIED"
    )
    assert result.get("finalized") is not True
    assert result.get("released") is not True


def test_durable_written_outcome_exposes_nonfatal_native_warnings() -> None:
    document = _Document()
    document.native_warnings = [
        "The FCStd is durable, but timestamp-backup cleanup could not be completed."
    ]

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document),
        {"document_name": "Model"},
        save_mode="save_as",
        destination="/work/Final.FCStd",
        overwrite=True,
    )

    assert result["success"] is True
    assert result["durability_verified"] is True
    assert result["warnings"] == document.native_warnings
    assert result["finalized"] is True
    assert result["released"] is True


def test_native_save_outcome_uses_save_disposition_without_legacy_alias(tmp_path) -> None:
    document = _OutcomeDocument()
    archive_path = tmp_path / "Model.FCStd"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Document.xml", "<Document />")
    document.FileName = str(archive_path)

    result = native_lifecycle_methods.save_document(
        _facade(document), {"document_name": "Model"}
    )

    assert result["success"] is True
    assert result["save_disposition"] == "unchanged"
    assert result["file_written"] is False
    assert result["resulting_clean"] is True
    assert result["file_evidence"]["sha256"] == "a" * 64
    assert result["invocation_baseline"]["sha256"] == "a" * 64
    assert "disposition" not in result
    assert document.calls == [("save_outcome", str(archive_path))]


def test_stable_archive_evidence_hashes_and_validates_live_fcstd(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        native_lifecycle_methods,
        "_stable_archive_evidence",
        _REAL_STABLE_ARCHIVE_EVIDENCE,
    )
    archive_path = tmp_path / "Verified.FCStd"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Document.xml", "<Document />")
        archive.writestr("GuiDocument.xml", "<GuiDocument />")

    evidence = native_lifecycle_methods._stable_archive_evidence(str(archive_path))

    assert evidence["size"] == archive_path.stat().st_size
    assert len(evidence["sha256"]) == 64
    assert evidence["archive"]["ok"] is True
    assert evidence["archive"]["member_count"] == 2
    assert evidence["archive"]["required_members"] == ["Document.xml"]


def test_written_save_fails_closed_when_live_archive_cannot_be_verified(monkeypatch) -> None:
    document = _Document()
    monkeypatch.setattr(
        native_lifecycle_methods,
        "_stable_archive_evidence",
        lambda _path: (_ for _ in ()).throw(ValueError("corrupt central directory")),
    )

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document), {"document_name": "Model"}
    )

    assert result["success"] is False
    assert result["error_code"] == "POST_SAVE_VERIFICATION_FAILED"
    assert result["file_written"] is True
    assert result.get("finalized") is not True
    assert result.get("released") is not True


def test_unchanged_save_compares_pre_invocation_baseline(monkeypatch, tmp_path) -> None:
    archive_path = tmp_path / "ChangedDuringSave.FCStd"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Document.xml", "<Document />")
    document = _OutcomeDocument()
    document.FileName = str(archive_path)
    evidence = iter(
        (
            _fake_evidence(str(archive_path), sha256="a" * 64, mtime_ns=7),
            _fake_evidence(str(archive_path), sha256="b" * 64, mtime_ns=8),
        )
    )
    monkeypatch.setattr(
        native_lifecycle_methods,
        "_stable_archive_evidence",
        lambda _path: next(evidence),
    )

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document), {"document_name": "Model"}
    )

    assert result["success"] is False
    assert result["error_code"] == "UNCHANGED_SAVE_BASELINE_CHANGED"
    assert result["file_written"] is False
    assert result.get("finalized") is not True
    assert result.get("released") is not True


def test_finalize_rechecks_live_clean_state_after_native_outcome() -> None:
    document = _Document()

    def outcome_then_mutate():
        outcome = _Document.saveWithOutcome(document)
        document.pending_file_changes = True
        return outcome

    document.saveWithOutcome = outcome_then_mutate

    result = native_lifecycle_methods.finalize_document_edit(
        _facade(document), {"document_name": "Model"}
    )

    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_REMAINS_MODIFIED"
    assert result["reported_clean"] is True
    assert result["live_clean"] is False
    assert result["resulting_clean"] is False
    assert result["finalized"] is False
    assert result["released"] is False


def test_live_clean_state_includes_canonical_save_failure_overlay() -> None:
    document = _Document()
    document.last_save_failed = True

    assert native_lifecycle_methods._resulting_clean(document, fallback=True) is False


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


def test_legacy_runtime_without_structured_save_outcomes_fails_closed() -> None:
    document = _Document()
    document.saveWithOutcome = None
    document.saveAsWithOutcome = None
    facade = _facade(document)

    saved = native_lifecycle_methods.save_document(
        facade, {"document_name": "Model"}
    )
    saved_as = native_lifecycle_methods.save_document_as(
        facade, {"document_name": "Model"}, "/work/New.FCStd"
    )

    assert saved["error_code"] == "NATIVE_SAVE_OUTCOME_UNAVAILABLE"
    assert saved_as["error_code"] == "NATIVE_SAVE_OUTCOME_UNAVAILABLE"
    assert document.calls == []


def test_save_and_finalize_cannot_clear_a_rollback_quarantine() -> None:
    document = _Document()
    facade = _facade(document)
    mutation_readiness.mark_quarantined(document, "rollback failed")
    try:
        saved = native_lifecycle_methods.save_document(
            facade, {"document_name": "Model"}
        )
        finalized = native_lifecycle_methods.finalize_document_edit(
            facade, {"document_name": "Model"}
        )

        assert saved["error_code"] == "DOCUMENT_QUARANTINED"
        assert saved["released"] is False
        assert finalized["error_code"] == "DOCUMENT_QUARANTINED"
        assert finalized["finalized"] is False
        assert document.calls == []
        assert mutation_readiness.document_readiness(document)["quarantined"] is True
    finally:
        mutation_readiness.clear_quarantine(document)
