"""Pure/mock tests for typed FCStd save and finalization behavior."""

from __future__ import annotations

import os
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace

import FreeCADGui
import pytest

from addon.FreeCADMCP.document_state import DocumentDirtyStateUnavailable
from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityError,
    capture_file_baseline,
)
from addon.FreeCADMCP.rpc_server.save_service import (
    ArchiveVerification,
    BaselineMismatchError,
    DestinationConflictError,
    DocumentDirtyError,
    DomainValidationError,
    FcstdVerificationError,
    LifecycleCallbackError,
    SaveService,
    SavedFileUnstableError,
    compare_file_to_baseline,
    verify_fcstd_archive,
)


def _write_fcstd(path, marker: str = "initial") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Document.xml", f"<Document marker='{marker}' />")
        archive.writestr("GuiDocument.xml", "<GuiDocument />")


class _FakeDocument:
    def __init__(self, path: str = ""):
        self.FileName = path
        self.Modified = True
        self.save_calls = 0
        self.save_as_calls: list[str] = []
        self.leave_dirty = False
        self.write_invalid = False

    def _write(self, path: str, marker: str) -> None:
        if self.write_invalid:
            with open(path, "wb") as handle:
                handle.write(b"not-a-zip")
        else:
            _write_fcstd(path, marker)

    def save(self):
        self.save_calls += 1
        self._write(self.FileName, f"save-{self.save_calls}")
        self.Modified = self.leave_dirty

    def saveAs(self, destination):
        self.save_as_calls.append(destination)
        self._write(destination, f"save-as-{len(self.save_as_calls)}")
        self.FileName = destination
        self.Modified = self.leave_dirty


@pytest.mark.unit
class TestSamePathSave:
    def test_gui_invocation_defers_archive_and_domain_validation(self, tmp_path):
        model = tmp_path / "phased.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        events: list[str] = []
        service = SaveService(
            archive_verifier=lambda _path: (
                events.append("archive")
                or ArchiveVerification(member_count=2, uncompressed_size=1)
            ),
            domain_validator=lambda _path, _profile: (
                events.append("domain") or {"ok": True}
            ),
        )

        preflight = service.prepare_save(
            document.FileName, expected_baseline=expected
        )
        invocation = service.invoke_save_gui(document, preflight)

        assert document.save_calls == 1
        assert events == []
        result = service.verify_saved_file(invocation)
        assert events == ["archive", "domain"]
        service.revalidate_saved_document_gui(document, result)

    def test_calls_document_save_without_a_path_and_verifies_archive(self, tmp_path):
        model = tmp_path / "model.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))

        result = SaveService().save_document(
            document,
            expected_baseline=expected,
            validation_profile="partdesign",
            domain_validator=lambda path, profile: {
                "ok": os.path.samefile(path, model),
                "profile": profile,
            },
        )

        assert document.save_calls == 1
        assert result.mode == "save"
        assert result.path == str(model.resolve())
        assert result.baseline.sha256 != expected.sha256
        assert result.archive.member_count == 2
        assert result.domain_validation["profile"] == "partdesign"
        assert result.to_dict()["ok"] is True

    def test_direct_app_save_clears_the_matching_gui_modified_flag(
        self, tmp_path, monkeypatch
    ):
        model = tmp_path / "gui-modified.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        gui_document = SimpleNamespace(Modified=True)
        monkeypatch.setattr(
            FreeCADGui,
            "getDocument",
            lambda name: gui_document if name == getattr(document, "Name", "") else None,
            raising=False,
        )
        document.Name = "GuiModified"

        SaveService().save_document(document, expected_baseline=expected)

        assert gui_document.Modified is False

    def test_unwritable_gui_modified_flag_fails_save_closed(
        self, tmp_path, monkeypatch
    ):
        class RefusesClear:
            @property
            def Modified(self):
                return True

            @Modified.setter
            def Modified(self, _value):
                return

        model = tmp_path / "gui-state-refused.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        document.Name = "GuiStateRefused"
        monkeypatch.setattr(
            FreeCADGui,
            "getDocument",
            lambda _name: RefusesClear(),
            raising=False,
        )

        with pytest.raises(DocumentDirtyStateUnavailable):
            SaveService().save_document(document, expected_baseline=expected)

    def test_external_change_blocks_save_before_freecad_is_called(self, tmp_path):
        model = tmp_path / "changed.FCStd"
        _write_fcstd(model, "one")
        expected = capture_file_baseline(model)
        _write_fcstd(model, "two")
        document = _FakeDocument(str(model))

        with pytest.raises(BaselineMismatchError) as raised:
            SaveService().save_document(document, expected_baseline=expected)

        assert document.save_calls == 0
        assert raised.value.stage == "preflight"
        assert raised.value.mutation_may_have_occurred is False
        assert raised.value.to_dict()["code"] == "BASELINE_MISMATCH"

    def test_replaced_file_identity_is_part_of_baseline_comparison(self, tmp_path):
        model = tmp_path / "identity.FCStd"
        replacement = tmp_path / "replacement.FCStd"
        _write_fcstd(model, "same")
        expected = capture_file_baseline(model)
        _write_fcstd(replacement, "same")
        stat = model.stat()
        os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        os.replace(replacement, model)

        with pytest.raises(BaselineMismatchError) as raised:
            compare_file_to_baseline(model, expected)

        assert "file_identity" in raised.value.details["differences"]

    def test_document_remaining_dirty_fails_after_save(self, tmp_path):
        model = tmp_path / "dirty.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        document.leave_dirty = True

        with pytest.raises(DocumentDirtyError) as raised:
            SaveService().save_document(document, expected_baseline=expected)

        assert document.save_calls == 1
        assert raised.value.mutation_may_have_occurred is True

    def test_invalid_fcstd_fails_after_stable_hash(self, tmp_path):
        model = tmp_path / "invalid.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        document.write_invalid = True

        with pytest.raises(FcstdVerificationError):
            SaveService().save_document(document, expected_baseline=expected)

    def test_concurrent_post_save_change_is_reported_as_unstable(self, tmp_path):
        model = tmp_path / "unstable.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        calls = 0

        def reader(path, *, platform=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                return capture_file_baseline(path, platform=platform)
            raise DocumentIdentityError("changed during hash")

        document = _FakeDocument(str(model))
        with pytest.raises(SavedFileUnstableError) as raised:
            SaveService(baseline_reader=reader).save_document(
                document, expected_baseline=expected
            )

        assert raised.value.stage == "post_save_hash"
        assert raised.value.mutation_may_have_occurred is True

    def test_failed_domain_validation_keeps_save_in_error_path(self, tmp_path):
        model = tmp_path / "domain.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))

        with pytest.raises(DomainValidationError) as raised:
            SaveService().save_document(
                document,
                expected_baseline=expected,
                domain_validator=lambda path, profile: {
                    "ok": False,
                    "reason": "Body.Tip mismatch",
                },
            )

        assert raised.value.details["reason"] == "Body.Tip mismatch"
        assert document.Modified is False


@pytest.mark.unit
class TestSaveAs:
    def test_first_save_holds_guard_through_verification_and_commit(self, tmp_path):
        destination = tmp_path / "first.FCStd"
        document = _FakeDocument()
        events: list[str] = []

        @contextmanager
        def guard(path):
            assert path == str(destination.resolve())
            events.append("guard-enter")
            try:
                yield
            finally:
                events.append("guard-exit")

        def commit(result):
            assert result.baseline.sha256 == capture_file_baseline(destination).sha256
            events.append("commit")

        result = SaveService().save_document_as(
            document,
            destination,
            source_baseline=None,
            destination_guard=guard,
            destination_commit=commit,
        )

        assert document.save_as_calls == [str(destination.resolve())]
        assert events == ["guard-enter", "commit", "guard-exit"]
        assert result.previous_path is None
        assert result.destination_preexisted is False

    def test_existing_destination_requires_overwrite_and_expected_hash(self, tmp_path):
        destination = tmp_path / "existing.FCStd"
        _write_fcstd(destination)
        document = _FakeDocument()

        with pytest.raises(DestinationConflictError):
            SaveService().save_document_as(
                document, destination, source_baseline=None
            )
        with pytest.raises(DestinationConflictError):
            SaveService().save_document_as(
                document,
                destination,
                source_baseline=None,
                overwrite=True,
            )

        assert document.save_as_calls == []

    def test_changed_destination_hash_is_rejected_without_writing(self, tmp_path):
        destination = tmp_path / "conflict.FCStd"
        _write_fcstd(destination)
        document = _FakeDocument()

        with pytest.raises(DestinationConflictError) as raised:
            SaveService().save_document_as(
                document,
                destination,
                source_baseline=None,
                overwrite=True,
                expected_destination_sha256="0" * 64,
            )

        assert raised.value.details["actual_sha256"]
        assert document.save_as_calls == []

    def test_saved_source_is_rechecked_while_destination_guard_is_held(self, tmp_path):
        source = tmp_path / "source.FCStd"
        destination = tmp_path / "destination.FCStd"
        _write_fcstd(source, "source")
        expected = capture_file_baseline(source)
        document = _FakeDocument(str(source))

        @contextmanager
        def guard(_path):
            _write_fcstd(source, "external-change")
            yield

        with pytest.raises(BaselineMismatchError):
            SaveService().save_document_as(
                document,
                destination,
                source_baseline=expected,
                destination_guard=guard,
            )

        assert document.save_as_calls == []

    def test_existing_hardlink_alias_of_source_is_rejected(self, tmp_path):
        source = tmp_path / "source.FCStd"
        destination = tmp_path / "alias.FCStd"
        _write_fcstd(source)
        try:
            os.link(source, destination)
        except (OSError, NotImplementedError):
            pytest.skip("hardlinks are unavailable on this filesystem")
        source_baseline = capture_file_baseline(source)
        destination_baseline = capture_file_baseline(destination)
        document = _FakeDocument(str(source))

        with pytest.raises(DestinationConflictError, match="aliases"):
            SaveService().save_document_as(
                document,
                destination,
                source_baseline=source_baseline,
                overwrite=True,
                expected_destination_sha256=destination_baseline.sha256,
            )


@pytest.mark.unit
class TestFinalization:
    def test_verified_baseline_is_committed_before_guarded_release(self, tmp_path):
        model = tmp_path / "final.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        events: list[tuple[str, str]] = []

        def mark_verified(result):
            events.append(("verified", result.baseline.sha256))
            return {"lease_state": "LOCKED_IDLE"}

        def release(result):
            events.append(("release", result.baseline.sha256))
            return {"lease_state": "UNLOCKED_SAVED"}

        finalized = SaveService().finalize_document_edit(
            document,
            save_mode="save",
            expected_baseline=expected,
            mark_verified=mark_verified,
            guarded_release=release,
        )

        assert [event[0] for event in events] == ["verified", "release"]
        assert events[0][1] == events[1][1]
        assert finalized.released is True
        assert finalized.to_dict()["release"]["lease_state"] == "UNLOCKED_SAVED"

    def test_release_failure_preserves_verified_save_diagnostics(self, tmp_path):
        model = tmp_path / "release-error.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))

        with pytest.raises(LifecycleCallbackError) as raised:
            SaveService().finalize_document_edit(
                document,
                save_mode="save",
                expected_baseline=expected,
                mark_verified=lambda result: None,
                guarded_release=lambda result: (_ for _ in ()).throw(
                    RuntimeError("sidecar CAS failed")
                ),
            )

        assert raised.value.stage == "guarded_release"
        assert raised.value.details["save_result"]["ok"] is True

    def test_callbacks_do_not_run_when_save_verification_fails(self, tmp_path):
        model = tmp_path / "bad-final.FCStd"
        _write_fcstd(model)
        expected = capture_file_baseline(model)
        document = _FakeDocument(str(model))
        document.write_invalid = True
        callbacks: list[str] = []

        with pytest.raises(FcstdVerificationError):
            SaveService().finalize_document_edit(
                document,
                save_mode="save",
                expected_baseline=expected,
                mark_verified=lambda result: callbacks.append("verified"),
                guarded_release=lambda result: callbacks.append("release"),
            )

        assert callbacks == []


@pytest.mark.unit
def test_archive_verification_requires_document_xml(tmp_path):
    path = tmp_path / "not-fcstd.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("other.txt", "readable but not FreeCAD")
    with pytest.raises(FcstdVerificationError) as raised:
        verify_fcstd_archive(path)
    assert raised.value.details["missing_members"] == ["Document.xml"]
