"""Focused tests for guarded schema-v2 sidecar persistence."""

from __future__ import annotations

import json
import os
import stat
import threading
import uuid
from dataclasses import replace
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.document_lease import sidecar as sidecar_mod
from addon.FreeCADMCP.document_lease.model import (
    MAX_PERSISTED_TASK_SUMMARY_CHARS,
    DocumentIdentity,
    FileBaseline,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    SaveAsMigration,
    SaveAsMigrationRole,
    token_fingerprint,
    sanitize_persisted_task_summary,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    MAX_SIDECAR_BYTES,
    SidecarConflictError,
    SidecarExistsError,
    SidecarMalformedError,
    SidecarNetworkPathError,
    SidecarPermissionError,
    SidecarStore,
    SidecarTooLargeError,
    _harden_directory_permissions,
    _harden_permissions,
    _assert_regular_not_symlink,
    parse_sidecar_bytes,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _owner() -> LeaseOwner:
    return LeaseOwner(
        addon_profile_id=_uuid(),
        addon_runtime_id=_uuid(),
        freecad_pid=100,
        freecad_process_started_at="2026-07-22T00:00:00Z",
        boot_id="boot",
        mcp_instance_id=_uuid(),
        mcp_pid=200,
        mcp_process_started_at="2026-07-22T00:00:01Z",
        hostname="host",
        client="pytest",
        agent_id="agent",
    )


def _record(document_path, *, token: str = "top-secret-token") -> LeaseRecord:
    return LeaseRecord(
        lease_id=_uuid(),
        generation=1,
        token_fingerprint=token_fingerprint(token),
        document=DocumentIdentity(
            session_uuid=_uuid(),
            name="Model",
            canonical_path=str(document_path),
            comparison_key=os.path.normcase(str(document_path)),
        ),
        owner=_owner(),
        state=LeaseState.LOCKED_IDLE,
        baseline=FileBaseline(
            mtime_ns=1, size=4, sha256="0" * 64, file_identity=None
        ),
        validation_complete=True,
    )


def _set_windows_test_dacl(path, sddl: str, *, protected: bool) -> None:
    """Install a test DACL using the same native boundary as production."""

    if os.name != "nt":
        raise RuntimeError("Windows test helper called on a non-Windows host")
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    convert_descriptor = (
        advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    )
    convert_descriptor.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.ULONG),
    ]
    convert_descriptor.restype = wintypes.BOOL
    get_dacl = advapi32.GetSecurityDescriptorDacl
    get_dacl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.BOOL),
    ]
    get_dacl.restype = wintypes.BOOL
    set_security = advapi32.SetNamedSecurityInfoW
    set_security.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    set_security.restype = wintypes.DWORD
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    descriptor = wintypes.LPVOID()
    assert convert_descriptor(sddl, 1, ctypes.byref(descriptor), None)
    try:
        present = wintypes.BOOL()
        defaulted = wintypes.BOOL()
        dacl = wintypes.LPVOID()
        assert get_dacl(
            descriptor,
            ctypes.byref(present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        )
        protection_flag = 0x80000000 if protected else 0x20000000
        result = set_security(
            str(path),
            1,  # SE_FILE_OBJECT
            0x00000004 | protection_flag,
            None,
            None,
            dacl,
            None,
        )
        assert result == 0
    finally:
        kernel32.LocalFree(descriptor)


@pytest.mark.unit
class TestSidecarSchema:
    def test_round_trip_contains_digest_but_never_raw_token(self, tmp_path):
        token = "raw-token-must-not-leak"
        record = _record(tmp_path / "model.FCStd", token=token)
        encoded = json.dumps(record.to_sidecar_dict()).encode()
        parsed = parse_sidecar_bytes(encoded)
        assert parsed == record
        assert token.encode() not in encoded
        assert "token_fingerprint" not in record.to_public_dict()
        assert token not in json.dumps(record.to_public_dict())

    def test_save_as_migration_round_trip_is_strict_and_publicly_redacted(
        self, tmp_path
    ):
        source = tmp_path / "source.FCStd"
        destination = tmp_path / "destination.FCStd"
        record = replace(
            _record(source),
            migration=SaveAsMigration(
                migration_id=_uuid(),
                source_canonical_path=str(source),
                source_comparison_key=os.path.normcase(str(source)),
                destination_canonical_path=str(destination),
                destination_comparison_key=os.path.normcase(str(destination)),
                role=SaveAsMigrationRole.SOURCE,
            ),
        )

        encoded = json.dumps(record.to_sidecar_dict()).encode()
        parsed = parse_sidecar_bytes(encoded)
        public = parsed.to_public_dict()

        assert parsed == record
        assert public["migration"]["migration_id"] == record.migration.migration_id
        assert public["migration"]["role"] == "source"
        assert "token_fingerprint" not in json.dumps(public)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda migration: migration.update(migration_id="not-a-uuid"),
            lambda migration: migration.update(role="peer"),
            lambda migration: migration.update(role="destination"),
            lambda migration: migration.update(unexpected=True),
            lambda migration: migration["source"].update(comparison_key=None),
            lambda migration: migration["destination"].update(
                canonical_path=migration["source"]["canonical_path"],
                comparison_key=migration["source"]["comparison_key"],
            ),
        ],
    )
    def test_parser_rejects_malformed_save_as_migration(
        self, tmp_path, mutate
    ):
        source = tmp_path / "source.FCStd"
        destination = tmp_path / "destination.FCStd"
        record = replace(
            _record(source),
            migration=SaveAsMigration(
                migration_id=_uuid(),
                source_canonical_path=str(source),
                source_comparison_key=os.path.normcase(str(source)),
                destination_canonical_path=str(destination),
                destination_comparison_key=os.path.normcase(str(destination)),
                role=SaveAsMigrationRole.SOURCE,
            ),
        )
        payload = record.to_sidecar_dict()
        mutate(payload["migration"])

        with pytest.raises(SidecarMalformedError):
            parse_sidecar_bytes(json.dumps(payload).encode())

    def test_parser_keeps_pre_linkage_schema_v2_records_compatible(self, tmp_path):
        payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
        payload.pop("migration")

        parsed = parse_sidecar_bytes(json.dumps(payload).encode())

        assert parsed.migration is None

    def test_parser_rejects_oversized_json_before_decoding(self):
        with pytest.raises(SidecarTooLargeError):
            parse_sidecar_bytes(b"{" + b"x" * MAX_SIDECAR_BYTES)

    def test_model_sidecar_serialization_omits_task_summary_by_default(self, tmp_path):
        record = replace(
            _record(tmp_path / "model.FCStd"),
            task_summary="private in-memory task metadata",
        )

        assert record.to_sidecar_dict()["lease"]["task_summary"] == ""
        assert (
            record.to_public_dict()["lease"]["task_summary"]
            == "private in-memory task metadata"
        )
        assert "token_fingerprint" not in record.to_public_dict()

    @pytest.mark.parametrize(
        "mutation",
        [
            lambda data: data.update(schema_version=99),
            lambda data: data.update(token_fingerprint="raw-token"),
            lambda data: data["lease"].update(state="MADE_UP"),
            lambda data: data.update(unexpected=True),
            lambda data: data["document_state"].update(dirty="yes"),
        ],
    )
    def test_parser_strictly_rejects_invalid_fields(self, tmp_path, mutation):
        payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
        mutation(payload)
        with pytest.raises(SidecarMalformedError):
            parse_sidecar_bytes(json.dumps(payload).encode())


@pytest.mark.unit
class TestSidecarStore:
    def test_task_summary_is_process_local_by_default(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        summary = "customer-specific Body → Sketch → Pad workflow"
        record = replace(
            _record(tmp_path / "model.FCStd"), task_summary=summary
        )

        SidecarStore().create(path, record)

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["lease"]["task_summary"] == ""
        assert summary not in path.read_text(encoding="utf-8")
        assert record.task_summary == summary
        assert record.to_public_dict()["lease"]["task_summary"] == summary

    def test_opt_in_task_summary_is_sanitized_and_bounded(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        summary = "  Build\tPad\x00for\u200b customer  " + "x" * 400
        record = replace(
            _record(tmp_path / "model.FCStd"), task_summary=summary
        )
        expected = sanitize_persisted_task_summary(summary)

        SidecarStore(persist_task_summary=True).create(path, record)

        persisted = json.loads(path.read_text(encoding="utf-8"))["lease"][
            "task_summary"
        ]
        assert persisted == expected
        assert persisted.startswith("Build Pad for customer ")
        assert len(persisted) <= MAX_PERSISTED_TASK_SUMMARY_CHARS
        assert all(character.isprintable() for character in persisted)
        assert record.task_summary == summary

        boundary = "x" * (MAX_PERSISTED_TASK_SUMMARY_CHARS - 1) + "  y"
        assert len(sanitize_persisted_task_summary(boundary)) <= (
            MAX_PERSISTED_TASK_SUMMARY_CHARS
        )

    def test_task_summary_persistence_policy_requires_boolean(self):
        with pytest.raises(TypeError, match="must be true or false"):
            SidecarStore(persist_task_summary="false")  # type: ignore[arg-type]

    def test_create_replace_delete_requires_exact_cas(self, tmp_path):
        store = SidecarStore()
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        current = _record(tmp_path / "model.FCStd")
        store.create(path, current)
        assert store.read(path) == current

        wrong = replace(current, generation=2)
        successor = current.revised(current_operation="Pad")
        with pytest.raises(SidecarConflictError):
            store.replace(path, successor, expected=wrong)
        assert store.read(path) == current

        store.replace(path, successor, expected=current)
        assert store.read(path) == successor
        with pytest.raises(SidecarConflictError):
            store.delete(path, expected=current)
        store.delete(path, expected=successor)
        assert not path.exists()

    def test_replace_rejects_skipped_record_revision(self, tmp_path):
        store = SidecarStore()
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        current = _record(tmp_path / "model.FCStd")
        store.create(path, current)
        skipped = replace(current, record_revision=current.record_revision + 2)
        with pytest.raises(SidecarConflictError):
            store.replace(path, skipped, expected=current)

    def test_existing_malformed_record_is_never_deleted_or_overwritten(self, tmp_path):
        store = SidecarStore()
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        path.write_text("{malformed", encoding="utf-8")
        _harden_permissions(path, strict=True)
        with pytest.raises(SidecarMalformedError):
            store.read(path)
        with pytest.raises(SidecarExistsError):
            store.create(path, _record(tmp_path / "model.FCStd"))
        with pytest.raises(SidecarMalformedError):
            store.delete(path, expected=_record(tmp_path / "model.FCStd"))
        assert path.read_text(encoding="utf-8") == "{malformed"

    def test_read_rejects_nonregular_sidecar(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        path.mkdir()

        with pytest.raises(SidecarMalformedError, match="regular file"):
            SidecarStore().read(path)

    def test_read_rejects_symlink_sidecar(self, tmp_path):
        target = tmp_path / "real-sidecar"
        target.write_text(
            json.dumps(_record(tmp_path / "model.FCStd").to_sidecar_dict()),
            encoding="utf-8",
        )
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        try:
            os.symlink(target, path)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation is unavailable")

        with pytest.raises(SidecarMalformedError, match="symlink or reparse"):
            SidecarStore().read(path)

    def test_reparse_attribute_is_rejected_without_following_target(self):
        class ReparsePath:
            @staticmethod
            def lstat():
                return SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o600,
                    st_file_attributes=getattr(
                        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
                    ),
                )

            @staticmethod
            def __str__():
                return "reparse-sidecar"

        with pytest.raises(SidecarMalformedError, match="reparse point"):
            _assert_regular_not_symlink(
                ReparsePath(), strict_permissions=False
            )

    def test_posix_mode_check_is_strict_only(self, monkeypatch):
        class BroadModePath:
            @staticmethod
            def lstat():
                return SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o644,
                    st_file_attributes=0,
                )

            @staticmethod
            def __str__():
                return "broad-mode-sidecar"

        monkeypatch.setattr(sidecar_mod.os, "name", "posix")
        _assert_regular_not_symlink(
            BroadModePath(), strict_permissions=False
        )
        with pytest.raises(
            SidecarPermissionError, match="exactly owner-only 0600"
        ):
            _assert_regular_not_symlink(
                BroadModePath(), strict_permissions=True
            )

    def test_two_simultaneous_creators_have_one_winner(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        barrier = threading.Barrier(2)
        results: list[str] = []

        def create(record):
            barrier.wait()
            try:
                SidecarStore().create(path, record)
                results.append("won")
            except SidecarExistsError:
                results.append("lost")

        threads = [
            threading.Thread(target=create, args=(_record(tmp_path / f"{i}.FCStd"),))
            for i in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert sorted(results) == ["lost", "won"]
        assert SidecarStore().read(path).state == LeaseState.LOCKED_IDLE

    def test_network_path_policy_is_fail_closed(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        store = SidecarStore(network_detector=lambda unused: True)
        with pytest.raises(SidecarNetworkPathError):
            store.create(path, _record(tmp_path / "model.FCStd"))
        assert not path.exists()

    @pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
    def test_created_sidecar_is_owner_only_on_posix(self, tmp_path):
        store = SidecarStore()
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        store.create(path, _record(tmp_path / "model.FCStd"))
        assert path.stat().st_mode & 0o077 == 0

    @pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
    @pytest.mark.parametrize("mode", [0o400, 0o640, 0o644, 0o700])
    def test_strict_read_requires_exact_0600_but_relaxed_read_accepts_mode(
        self, tmp_path, mode
    ):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        record = _record(tmp_path / "model.FCStd")
        path.write_text(
            json.dumps(record.to_sidecar_dict()), encoding="utf-8"
        )
        path.chmod(mode)

        with pytest.raises(SidecarPermissionError, match="exactly owner-only 0600"):
            SidecarStore(strict_permissions=True).read(path)
        assert SidecarStore(strict_permissions=False).read(path) == record

        path.chmod(0o600)
        assert SidecarStore(strict_permissions=True).read(path) == record

    @pytest.mark.skipif(os.name != "nt", reason="Windows DACL semantics only")
    def test_strict_windows_read_rejects_extra_principal_but_relaxed_read_allows_it(
        self, tmp_path
    ):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        record = _record(tmp_path / "model.FCStd")
        SidecarStore().create(path, record)

        _set_windows_test_dacl(
            path,
            "D:P(A;;FA;;;SY)(A;;FA;;;OW)(A;;FR;;;WD)",
            protected=True,
        )

        with pytest.raises(SidecarPermissionError, match="owner-only Windows DACL"):
            SidecarStore(strict_permissions=True).read(path)
        assert SidecarStore(strict_permissions=False).read(path) == record

    @pytest.mark.skipif(os.name != "nt", reason="Windows DACL semantics only")
    def test_strict_windows_read_rejects_unprotected_exact_aces(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        record = _record(tmp_path / "model.FCStd")
        SidecarStore().create(path, record)

        _set_windows_test_dacl(
            path,
            "D:(A;;FA;;;SY)(A;;FA;;;OW)",
            protected=False,
        )

        with pytest.raises(SidecarPermissionError, match="not protected"):
            SidecarStore(strict_permissions=True).read(path)
        assert SidecarStore(strict_permissions=False).read(path) == record

    @pytest.mark.skipif(os.name != "nt", reason="Windows DACL semantics only")
    def test_strict_windows_replace_and_delete_reject_broadened_guard(self, tmp_path):
        path = tmp_path / "model.FCStd.freecad-mcp.lock"
        record = _record(tmp_path / "model.FCStd")
        store = SidecarStore()
        store.create(path, record)
        successor = record.revised(current_operation="Pad")
        guard_path = sidecar_mod.guard_path_for(path)

        _set_windows_test_dacl(
            guard_path,
            "D:P(A;;FA;;;SY)(A;;FA;;;OW)(A;;FR;;;WD)",
            protected=True,
        )

        with pytest.raises(SidecarPermissionError, match="guard file"):
            store.replace(path, successor, expected=record)
        with pytest.raises(SidecarPermissionError, match="guard file"):
            store.delete(path, expected=record)
        assert SidecarStore(strict_permissions=False).read(path) == record

    @pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits only")
    def test_file_and_directory_owner_only_modes_are_distinct(self, tmp_path):
        artifact = tmp_path / "artifact.FCStd"
        artifact.write_bytes(b"snapshot")
        artifact.chmod(0o666)
        recovery = tmp_path / "recovery"
        recovery.mkdir(mode=0o777)
        recovery.chmod(0o777)

        # A string path covers the profile-secret regression: the hardener
        # must normalize os.PathLike values before using Path.stat().
        _harden_permissions(str(artifact), strict=True)
        _harden_directory_permissions(recovery, strict=True)

        assert artifact.stat().st_mode & 0o777 == 0o600
        assert recovery.stat().st_mode & 0o777 == 0o700
