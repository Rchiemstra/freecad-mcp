"""Unit tests for the FreeCAD-independent lease-v2 model and identity layer."""

from __future__ import annotations

import os
import uuid
import pytest

from addon.FreeCADMCP.document_lease.identity import (
    DocumentIdentityService,
    DuplicateDocumentError,
    IdentityMismatchError,
    UnknownDocumentError,
    canonicalize_path,
    capture_file_baseline,
)
from addon.FreeCADMCP.document_lease.model import (
    ALLOWED_TRANSITIONS,
    DocumentSelector,
    InvalidTransitionError,
    LeaseCredential,
    LeaseState,
    token_fingerprint,
    token_matches,
    validate_transition,
)


@pytest.mark.unit
class TestLeaseStateModel:
    def test_every_state_has_an_explicit_transition_set(self):
        assert set(ALLOWED_TRANSITIONS) == set(LeaseState)
        assert LeaseState.LOCKED_EDITING in ALLOWED_TRANSITIONS[LeaseState.LOCKED_IDLE]
        assert LeaseState.LOCKED_IDLE in ALLOWED_TRANSITIONS[LeaseState.STALE]
        assert LeaseState.RELEASING in ALLOWED_TRANSITIONS[LeaseState.USER_INTERVENED]
        assert LeaseState.RELEASING in ALLOWED_TRANSITIONS[LeaseState.UNLOCKED_DIRTY]

    def test_invalid_transition_is_rejected(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition(LeaseState.LOCKED_EDITING, LeaseState.RELEASING)
        with pytest.raises(InvalidTransitionError):
            validate_transition(LeaseState.USER_INTERVENED, LeaseState.LOCKED_EDITING)

    def test_token_fingerprint_is_stable_and_constant_time_comparable(self):
        token = "correct horse battery staple"
        digest = token_fingerprint(token)
        assert digest.startswith("sha256:")
        assert token not in digest
        assert token_matches(token, digest)
        assert not token_matches("wrong", digest)
        assert not token_matches("", digest)
        assert not token_matches(token, "not-a-digest")

    def test_addon_credential_repr_never_exposes_raw_token(self):
        token = "raw-bearer-secret-must-not-appear"
        credential = LeaseCredential(
            lease_id=str(uuid.uuid4()),
            document_session_uuid=str(uuid.uuid4()),
            generation=1,
            token=token,
            mcp_instance_id=str(uuid.uuid4()),
        )

        rendered = repr(credential)
        assert token not in rendered
        assert "token=" not in rendered


class _FakeDocument:
    def __init__(self, name: str, filename: str = ""):
        self.Name = name
        self.FileName = filename


@pytest.mark.unit
class TestDocumentIdentityService:
    def test_windows_path_comparison_is_case_and_separator_insensitive(self):
        first_canonical, first_key = canonicalize_path(
            r"C:\Models\Assembly.FCStd", platform="windows"
        )
        second_canonical, second_key = canonicalize_path(
            r"c:/models/./ASSEMBLY.fcstd", platform="windows"
        )
        assert first_canonical != ""
        assert second_canonical != ""
        assert first_key == second_key

    def test_document_proxy_gets_one_addon_issued_uuid(self, tmp_path):
        model = tmp_path / "model.FCStd"
        model.write_bytes(b"FCStd")
        doc = _FakeDocument("Model", str(model))
        service = DocumentIdentityService()
        first = service.register_document(doc)
        second = service.register_document(doc)
        assert first.session_uuid == second.session_uuid
        assert uuid.UUID(first.session_uuid)
        assert service.resolve(first.session_uuid) == first

    def test_registered_proxy_path_change_requires_explicit_update(self, tmp_path):
        source = tmp_path / "source.FCStd"
        target = tmp_path / "target.FCStd"
        source.write_bytes(b"source")
        target.write_bytes(b"target")
        doc = _FakeDocument("Model", str(source))
        service = DocumentIdentityService()
        identity = service.register_document(doc)

        doc.FileName = str(target)
        with pytest.raises(IdentityMismatchError):
            service.register_document(doc)

        updated = service.update_path(identity.session_uuid, target)
        assert service.register_document(doc) == updated

    def test_registered_proxy_file_replacement_is_detected(self, tmp_path):
        model = tmp_path / "model.FCStd"
        replacement = tmp_path / "replacement.FCStd"
        model.write_bytes(b"original")
        replacement.write_bytes(b"replacement")
        doc = _FakeDocument("Model", str(model))
        service = DocumentIdentityService()
        service.register_document(doc)

        model.unlink()
        replacement.replace(model)
        with pytest.raises(IdentityMismatchError):
            service.register_document(doc)

    def test_save_as_preserves_uuid_and_old_path_alias(self, tmp_path):
        source = tmp_path / "source.FCStd"
        target = tmp_path / "target.FCStd"
        source.write_bytes(b"source")
        target.write_bytes(b"target")
        service = DocumentIdentityService()
        identity = service.register(name="Model", path=source)
        updated = service.update_path(identity.session_uuid, target)
        assert updated.session_uuid == identity.session_uuid
        assert service.resolve(
            DocumentSelector(canonical_path=str(source))
        ).session_uuid == identity.session_uuid
        assert service.resolve(
            DocumentSelector(canonical_path=str(target))
        ).session_uuid == identity.session_uuid

    def test_reload_rebind_preserves_uuid_and_replaces_only_live_proxy(self, tmp_path):
        source = tmp_path / "Model.FCStd"
        source.write_bytes(b"source")
        original = _FakeDocument("Model", str(source))
        replacement = _FakeDocument("Model", str(source))
        service = DocumentIdentityService()
        identity = service.register_document(original)

        rebound = service.rebind_document(identity.session_uuid, replacement)

        assert rebound.session_uuid == identity.session_uuid
        assert service.inspect_registered_document(
            identity.session_uuid, replacement
        ) == rebound
        with pytest.raises(IdentityMismatchError):
            service.inspect_registered_document(identity.session_uuid, original)

    def test_failed_reload_rebind_leaves_original_proxy_authoritative(self, tmp_path):
        source = tmp_path / "Model.FCStd"
        conflict = tmp_path / "Other.FCStd"
        source.write_bytes(b"source")
        conflict.write_bytes(b"other")
        original = _FakeDocument("Model", str(source))
        replacement = _FakeDocument("Model", str(conflict))
        service = DocumentIdentityService()
        identity = service.register_document(original)
        service.register(name="Other", path=conflict)

        with pytest.raises(DuplicateDocumentError):
            service.rebind_document(identity.session_uuid, replacement)

        assert service.inspect_registered_document(
            identity.session_uuid, original
        ) == identity
        with pytest.raises(IdentityMismatchError):
            service.inspect_registered_document(identity.session_uuid, replacement)

    def test_duplicate_path_and_file_identity_are_rejected(self, tmp_path):
        source = tmp_path / "source.FCStd"
        alias = tmp_path / "hardlink.FCStd"
        source.write_bytes(b"same inode")
        service = DocumentIdentityService()
        service.register(name="First", path=source)
        with pytest.raises(DuplicateDocumentError):
            service.register(name="Second", path=source)
        try:
            os.link(source, alias)
        except OSError:
            pytest.skip("hardlinks are unavailable on this filesystem")
        with pytest.raises(DuplicateDocumentError):
            service.register(name="Third", path=alias)

    def test_typed_open_preflight_rejects_path_and_hardlink_before_open(
        self, tmp_path
    ):
        source = tmp_path / "source.FCStd"
        alias = tmp_path / "hardlink.FCStd"
        unused = tmp_path / "unused.FCStd"
        source.write_bytes(b"same inode")
        unused.write_bytes(b"different")
        service = DocumentIdentityService()
        service.register(name="First", path=source)

        with pytest.raises(DuplicateDocumentError):
            service.assert_open_path_available(source)
        try:
            os.link(source, alias)
        except OSError:
            pytest.skip("hardlinks are unavailable on this filesystem")
        with pytest.raises(DuplicateDocumentError):
            service.assert_open_path_available(alias)

        canonical, comparison, file_identity = (
            service.assert_open_path_available(unused)
        )
        assert canonical
        assert comparison
        assert file_identity is not None

    def test_all_selector_fields_are_assertions(self, tmp_path):
        first = tmp_path / "first.FCStd"
        second = tmp_path / "second.FCStd"
        first.write_bytes(b"1")
        second.write_bytes(b"2")
        service = DocumentIdentityService()
        first_id = service.register(name="First", path=first)
        service.register(name="Second", path=second)
        with pytest.raises(IdentityMismatchError):
            service.resolve(
                DocumentSelector(
                    document_session_uuid=first_id.session_uuid,
                    document_name="Second",
                )
            )

    def test_unregister_makes_identity_non_live(self):
        service = DocumentIdentityService()
        identity = service.register(name="Unsaved")
        service.unregister(identity.session_uuid)
        with pytest.raises(UnknownDocumentError):
            service.resolve(identity.session_uuid)

    def test_baseline_rejects_no_data_and_captures_hash(self, tmp_path):
        model = tmp_path / "model.FCStd"
        model.write_bytes(b"archive bytes")
        baseline = capture_file_baseline(model)
        assert baseline.size == len(b"archive bytes")
        assert len(baseline.sha256) == 64
        assert baseline.file_identity is not None
