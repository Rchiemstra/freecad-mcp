"""Headless tests for token-safe lease status presentation."""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP import lock_indicator
from addon.FreeCADMCP.document_lease.model import FileBaseline


def _v2_record(*, name: str = "Part", state: str = "LOCKED_IDLE") -> dict:
    return {
        "schema_version": 2,
        "record_kind": "freecad-mcp-document-lease",
        "lease_id": "lease-one",
        "generation": 3,
        "token": "raw-token-must-never-render",
        "token_fingerprint": "sha256:fingerprint-must-never-render",
        "document": {
            "session_uuid": "document-one",
            "name": name,
            "canonical_path": f"C:/models/{name}.FCStd",
        },
        "owner": {
            "mcp_instance_id": "instance-one",
            "mcp_pid": 42,
            "hostname": "workstation",
            "client": "codex",
            "agent_id": "agent-one",
            "session_token": "nested-session-secret",
        },
        "lease": {
            "state": state,
            "acquired_at": "2026-07-22T10:00:00Z",
            "last_heartbeat_at": "2026-07-22T10:00:10Z",
            "current_operation": "Create Pad",
            "task_summary": "Body lifecycle raw-token-must-never-render",
        },
        "document_state": {
            "dirty": True,
            "user_intervened": state == "USER_INTERVENED",
            "baseline": {"sha256": "file-content-hash"},
            "error": None,
        },
    }


def test_recursive_redaction_removes_raw_and_derived_credentials():
    safe = lock_indicator._redact_secrets(_v2_record())

    assert "token" not in safe
    assert "token_fingerprint" not in safe
    assert "session_token" not in safe["owner"]
    assert safe["lease_id"] == "lease-one"


def test_v2_status_and_tooltip_are_token_safe():
    status, tooltip = lock_indicator._lease_lines(_v2_record())

    rendered = status + tooltip
    assert "Part.FCStd" in status
    assert "Create Pad" in status
    assert "Unsaved" in status
    assert "raw-token-must-never-render" not in rendered
    assert "fingerprint-must-never-render" not in rendered
    assert "nested-session-secret" not in rendered
    assert "[redacted]" in tooltip
    assert "Recovery baseline: available" in tooltip


def test_legacy_status_is_supported_without_rendering_token():
    legacy = {
        "lease_id": "legacy-one",
        "doc_key": "C:/models/Legacy.FCStd",
        "doc_name": "Legacy",
        "token": "legacy-raw-token",
        "state": "LOCKED_EDITING",
        "client": "cursor",
        "instance_id": "legacy-instance",
        "document_dirty": False,
        "baseline_hash": "file-hash-not-a-credential",
    }

    status, tooltip = lock_indicator._lease_lines(legacy)

    assert "Legacy.FCStd" in status
    assert "legacy-raw-token" not in status + tooltip
    assert "Recovery baseline: available" in tooltip


def test_selected_or_active_document_wins_over_unrelated_error():
    active = _v2_record(name="Active", state="LOCKED_IDLE")
    unrelated = _v2_record(name="Other", state="LOCKED_ERROR")
    unrelated["lease_id"] = "lease-two"
    unrelated["document"]["session_uuid"] = "document-two"

    selected = lock_indicator._select_preferred_lease(
        [unrelated, active], ["C:\\models\\ACTIVE.FCStd"]
    )

    assert selected is active


def test_urgent_state_is_fallback_when_document_has_no_match():
    healthy = _v2_record(name="Healthy", state="LOCKED_IDLE")
    stale = _v2_record(name="Stale", state="STALE")
    stale["lease_id"] = "lease-stale"

    selected = lock_indicator._select_preferred_lease(
        [healthy, stale], ["MissingDocument"]
    )

    assert selected is stale


def test_all_v2_state_families_have_distinct_semantic_colors():
    blue = lock_indicator._state_presentation("LOCKED_EDITING")[1]
    purple = lock_indicator._state_presentation("LOCKED_SAVING")[1]
    amber = lock_indicator._state_presentation("STALE")[1]
    red = lock_indicator._state_presentation("USER_INTERVENED")[1]

    assert len({blue, purple, amber, red}) == 4
    assert lock_indicator._state_presentation("RELEASING")[1] == purple
    assert lock_indicator._state_presentation("CANCELLING")[1] == amber
    assert lock_indicator._state_presentation("UNLOCKED_DIRTY")[1] == red
    assert lock_indicator._state_presentation("SIDECAR_MALFORMED")[1] == red


def test_public_refresh_only_emits_gui_bridge_signal(monkeypatch):
    calls = []

    class Signal:
        def emit(self):
            calls.append("queued")

    class Bridge:
        refresh_requested = Signal()

    monkeypatch.setattr(lock_indicator, "_refresh_bridge", Bridge())
    lock_indicator.refresh_lock_indicator()

    assert calls == ["queued"]


def test_malformed_foreign_sidecar_becomes_red_shadow(tmp_path, monkeypatch):
    model = tmp_path / "Foreign.FCStd"
    model.write_bytes(b"model")
    sidecar = tmp_path / "Foreign.FCStd.freecad-mcp.lock"
    sidecar.write_text("not-json", encoding="utf-8")

    class Identity:
        session_uuid = "local-document"
        name = "Foreign"
        canonical_path = str(model)

        def to_dict(self):
            return {
                "session_uuid": self.session_uuid,
                "name": self.name,
                "canonical_path": self.canonical_path,
            }

    class Store:
        def read(self, _path):
            raise ValueError("invalid sidecar")

    service = SimpleNamespace(
        list_records=lambda: [],
        identity_service=SimpleNamespace(resolve=lambda _selector: Identity()),
        sidecar_store=Store(),
    )
    document = SimpleNamespace(Name="Foreign", Modified=False)
    freecad = SimpleNamespace(listDocuments=lambda: {"Foreign": document})
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)

    shadows = lock_indicator._foreign_shadow_leases(service)

    assert len(shadows) == 1
    view = lock_indicator._lease_view(shadows[0])
    assert view["source"] == "unknown_sidecar"
    assert view["state"] == "SIDECAR_MALFORMED"
    assert lock_indicator._state_presentation(view["state"])[1] == "#b42318"


class _Action:
    def __init__(self, name: str, enabled: bool = True):
        self._name = name
        self._enabled = enabled

    def objectName(self):
        return self._name

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, value):
        self._enabled = bool(value)


def test_known_mutating_actions_are_disabled_and_restored_for_active_owner():
    lock_indicator._deterred_actions.clear()
    lease = _v2_record(name="Active", state="LOCKED_IDLE")
    save = _Action("Std_Save")
    pad = _Action("PartDesign_Pad")
    camera = _Action("Std_ViewFitAll")
    unavailable = _Action("Std_Undo", enabled=False)
    actions = [save, pad, camera, unavailable]

    blocked = lock_indicator._update_command_deterrence(
        [lease], hints=["C:/models/Active.FCStd"], actions=actions
    )

    assert blocked is True
    assert save.isEnabled() is False
    assert pad.isEnabled() is False
    assert camera.isEnabled() is True
    assert unavailable.isEnabled() is False

    intervened = _v2_record(name="Active", state="USER_INTERVENED")
    blocked = lock_indicator._update_command_deterrence(
        [intervened], hints=["Active"], actions=actions
    )

    assert blocked is False
    assert save.isEnabled() is True
    assert pad.isEnabled() is True
    assert camera.isEnabled() is True
    assert unavailable.isEnabled() is False
    assert lock_indicator._deterred_actions == {}


def test_all_known_standard_mutation_bypasses_are_deterred():
    for command in (
        "Std_SaveAll",
        "Std_Transform",
        "Std_DlgMacroRecord",
        "Std_DlgMacroExecuteDirect",
    ):
        assert lock_indicator._is_known_mutating_action(_Action(command)) is True


def test_same_basename_at_another_canonical_path_does_not_deter_active_document():
    lock_indicator._deterred_actions.clear()
    lease = _v2_record(name="Leased", state="LOCKED_EDITING")
    lease["document"]["canonical_path"] = "C:/leased/Shared.FCStd"
    action = _Action("Std_SaveAll")

    blocked = lock_indicator._update_command_deterrence(
        [lease],
        hints=["D:/active/Shared.FCStd", "Leased"],
        actions=[action],
    )

    assert blocked is False
    assert action.isEnabled() is True


def test_session_uuid_hint_is_authoritative_over_same_document_name():
    expected_session = "b2aef45e-780c-4f92-a510-9cc5a3a54fd4"
    other_session = "ee6ef57d-e751-4070-b05a-6e4ccac2a0c9"
    lease = _v2_record(name="Shared", state="LOCKED_IDLE")
    lease["document"]["session_uuid"] = expected_session

    assert lock_indicator._lease_matches_hints(lease, [expected_session, "Shared"])
    assert not lock_indicator._lease_matches_hints(lease, [other_session, "Shared"])


def test_unrelated_leased_document_does_not_disable_active_document_actions():
    lock_indicator._deterred_actions.clear()
    action = _Action("Std_Save")

    blocked = lock_indicator._update_command_deterrence(
        [_v2_record(name="Other", state="LOCKED_EDITING")],
        hints=["Active"],
        actions=[action],
    )

    assert blocked is False
    assert action.isEnabled() is True


def test_local_recovery_capabilities_exclude_foreign_and_unconfirmed_records():
    document = SimpleNamespace(Modified=True)
    taken = _v2_record(state="USER_INTERVENED")
    taken["document_state"]["snapshot_id"] = "16cd2790-0ae5-47d0-ad75-b463e665bf1a"
    capabilities = lock_indicator._local_recovery_capabilities(taken, document)
    assert capabilities == {
        "takeover": False,
        "keep_dirty": True,
        "save_and_clear": True,
        "restore_baseline": True,
    }

    foreign = _v2_record(state="STALE")
    foreign["source"] = "foreign_sidecar"
    assert lock_indicator._local_recovery_capabilities(foreign, document) == {
        "takeover": False,
        "keep_dirty": False,
        "save_and_clear": False,
        "restore_baseline": False,
    }

    imported = _v2_record(state="STALE")
    imported["source"] = "foreign_recovery"
    imported["local_document"] = {
        "session_uuid": "local-document",
        "name": "Part",
        "canonical_path": "C:/models/Part.FCStd",
        "comparison_key": "c:/models/part.fcstd",
        "file_identity": None,
    }
    assert lock_indicator._lease_view(imported)["document_session_uuid"] == (
        "local-document"
    )
    assert lock_indicator._local_recovery_capabilities(imported, document) == {
        "takeover": True,
        "keep_dirty": False,
        "save_and_clear": False,
        "restore_baseline": False,
    }


def test_confirmed_foreign_takeover_uses_fresh_identity_and_modified_state():
    lease = _v2_record(state="STALE")
    lease["source"] = "foreign_recovery"
    lease["local_document"] = {
        "session_uuid": "local-document",
        "name": "Part",
        "canonical_path": "C:/models/Part.FCStd",
        "comparison_key": "c:/models/part.fcstd",
        "file_identity": None,
    }
    document = SimpleNamespace(Name="Part", Modified=True)
    live_identity = object()
    calls = []

    class Record:
        @staticmethod
        def to_public_dict():
            return {"lease": {"state": "USER_INTERVENED"}}

    class Identities:
        @staticmethod
        def inspect_registered_document(session_uuid, exact_document):
            assert session_uuid == "local-document"
            assert exact_document is document
            calls.append("inspect")
            return live_identity

    class Service:
        identity_service = Identities()

        @staticmethod
        def confirmed_takeover_foreign_recovery(selector, **kwargs):
            calls.append((selector, kwargs))
            return Record()

    result = lock_indicator._confirmed_foreign_takeover(
        lease,
        Service(),
        document,
        reason="Confirmed in modal",
    )

    assert result["lease"]["state"] == "USER_INTERVENED"
    assert calls[0] == "inspect"
    selector, kwargs = calls[1]
    assert selector == {"document_session_uuid": "local-document"}
    assert kwargs == {
        "live_document": live_identity,
        "confirmed": True,
        "document_dirty": True,
        "reason": "Confirmed in modal",
    }


def test_confirmed_foreign_takeover_requires_authoritative_modified_state():
    lease = _v2_record(state="STALE")
    lease["source"] = "foreign_recovery"
    lease["local_document"] = {
        "session_uuid": "local-document",
        "name": "Part",
        "canonical_path": "C:/models/Part.FCStd",
    }
    calls = []
    service = SimpleNamespace(
        identity_service=SimpleNamespace(
            inspect_registered_document=lambda *_args: object()
        ),
        confirmed_takeover_foreign_recovery=lambda *_args, **_kwargs: calls.append(
            "takeover"
        ),
    )

    with pytest.raises(RuntimeError, match="Document.Modified"):
        lock_indicator._confirmed_foreign_takeover(
            lease,
            service,
            SimpleNamespace(Name="Part"),
            reason="Confirmed in modal",
        )

    assert calls == []


def test_keep_dirty_helper_uses_session_identity_without_credentials():
    lease = _v2_record(state="USER_INTERVENED")
    calls = []

    class Record:
        @staticmethod
        def to_public_dict():
            return {"lease": {"state": "UNLOCKED_DIRTY"}}

    service = SimpleNamespace(
        acknowledge_local_dirty=lambda selector, **kwargs: (
            calls.append((selector, kwargs)) or Record()
        )
    )

    result = lock_indicator._acknowledge_selected_dirty(
        lease, service, SimpleNamespace(Modified=True)
    )

    assert result["lease"]["state"] == "UNLOCKED_DIRTY"
    assert calls[0][0] == {"document_session_uuid": "document-one"}
    assert "token" not in repr(calls)


def test_verified_local_save_uses_worker_validation_then_local_cas_release():
    lease = _v2_record(state="USER_INTERVENED")
    baseline = FileBaseline(mtime_ns=1, size=2, sha256="a" * 64)
    lease["document_state"]["baseline"] = baseline.to_dict()
    events = []

    class Saved:
        def __init__(self):
            self.baseline = baseline

        @staticmethod
        def to_dict():
            return {"ok": True, "path": "C:/models/Part.FCStd"}

    class Saver:
        @staticmethod
        def prepare_save(_source_path, **kwargs):
            events.append(("prepare", kwargs["expected_baseline"]))
            return "preflight"

        @staticmethod
        def invoke_save_gui(document, preflight):
            assert preflight == "preflight"
            events.append(("invoke", document.Modified))
            document.Modified = False
            return SimpleNamespace(comparison_key="comparison-key")

        @staticmethod
        def verify_saved_file(_invocation, **kwargs):
            events.append(("verify",))
            assert kwargs["domain_validator"]("C:/models/Part.FCStd", "local-recovery")[
                "ok"
            ]
            return Saved()

        @staticmethod
        def revalidate_saved_document_gui(_document, _saved):
            events.append(("revalidate",))

    class IdentityService:
        @staticmethod
        def inspect_registered_document(session_uuid, _document):
            assert session_uuid == "document-one"
            events.append(("identity",))
            return SimpleNamespace(
                session_uuid=session_uuid,
                name="Part",
                canonical_path="C:/models/Part.FCStd",
                comparison_key="comparison-key",
            )

    class Dispatcher:
        @staticmethod
        def submit(task, **_kwargs):
            events.append(("dispatch",))
            return task()

    class Service:
        identity_service = IdentityService()

        @staticmethod
        def get(selector):
            assert selector == {"document_session_uuid": "document-one"}
            return lease

        @staticmethod
        def complete_local_save_and_clear(selector, **kwargs):
            events.append(("release", selector, kwargs))
            return {
                "lease": {"state": "UNLOCKED_SAVED"},
                "document_state": {"snapshot_id": "snapshot-one"},
            }

    discarded = []
    document = SimpleNamespace(Name="Part", Modified=True)
    result = lock_indicator._verified_local_save_and_clear(
        lease,
        Service(),
        document,
        save_service=Saver(),
        expectation_builder=lambda _document: {"objects": ["Body"]},
        worker_validator=lambda path, name, profile, expected: {
            "ok": path.endswith("Part.FCStd")
            and name == "Part"
            and profile == "local-recovery"
            and expected == {"objects": ["Body"]}
        },
        snapshot_discarder=discarded.append,
        gui_dispatcher=Dispatcher(),
    )

    assert result["release"]["lease"]["state"] == "UNLOCKED_SAVED"
    assert [event[0] for event in events] == [
        "dispatch",
        "identity",
        "prepare",
        "dispatch",
        "invoke",
        "verify",
        "dispatch",
        "identity",
        "revalidate",
        "release",
    ]
    release = events[-1]
    assert release[2]["document_modified"] is False
    assert release[2]["baseline_validated"] is True
    assert discarded == [result["release"]]
    assert "token" not in repr(events)


def test_local_save_pipeline_thread_affinity_and_phase_order(tmp_path):
    path = str(tmp_path / "Part.FCStd")
    lease = _v2_record(state="USER_INTERVENED")
    lease["document"]["canonical_path"] = path
    lease["document"]["comparison_key"] = "part-comparison"
    baseline = FileBaseline(mtime_ns=1, size=2, sha256="b" * 64)
    lease["document_state"]["baseline"] = baseline.to_dict()
    events = []
    gui_threads = []
    caller_thread = threading.get_ident()

    def note(name):
        events.append((name, threading.get_ident()))

    class Document:
        Name = "Part"

        def __init__(self):
            self._modified = True

        @property
        def Modified(self):
            note("modified-read")
            return self._modified

        @Modified.setter
        def Modified(self, value):
            self._modified = bool(value)

    document = Document()

    class Dispatcher:
        @staticmethod
        def submit(task, *, timeout, request_id):
            assert timeout == lock_indicator._LOCAL_SAVE_GUI_TIMEOUT
            assert request_id.startswith("local-save-")
            result = []
            failure = []

            def run():
                gui_threads.append(threading.get_ident())
                try:
                    result.append(task())
                except BaseException as exc:
                    failure.append(exc)

            thread = threading.Thread(target=run, name="mock-freecad-gui")
            thread.start()
            thread.join()
            if failure:
                raise failure[0]
            return result[0]

    identity_calls = 0

    class IdentityService:
        @staticmethod
        def inspect_registered_document(session_uuid, exact_document):
            nonlocal identity_calls
            assert session_uuid == "document-one"
            assert exact_document is document
            identity_calls += 1
            note(f"identity-{identity_calls}")
            return SimpleNamespace(
                session_uuid=session_uuid,
                name="Part",
                canonical_path=path,
                comparison_key="part-comparison",
            )

    class Service:
        identity_service = IdentityService()

        @staticmethod
        def get(selector):
            note("get")
            assert selector == {"document_session_uuid": "document-one"}
            return lease

        @staticmethod
        def complete_local_save_and_clear(selector, **kwargs):
            note("cas-clear")
            assert selector == {"document_session_uuid": "document-one"}
            assert kwargs["verified_baseline"] is baseline
            assert kwargs["baseline_validated"] is True
            assert kwargs["document_modified"] is False
            return {"lease": {"state": "UNLOCKED_SAVED"}}

    class Saved:
        def __init__(self, verified_baseline):
            self.baseline = verified_baseline

        @staticmethod
        def to_dict():
            return {"ok": True, "path": path}

    class Saver:
        @staticmethod
        def prepare_save(source_path, **kwargs):
            note("prepare-hash")
            assert source_path == path
            assert kwargs["expected_baseline"] is not None
            return "preflight"

        @staticmethod
        def invoke_save_gui(exact_document, preflight):
            note("invoke-save")
            assert exact_document is document
            assert preflight == "preflight"
            exact_document.Modified = False
            return SimpleNamespace(comparison_key="part-comparison")

        @staticmethod
        def verify_saved_file(_invocation, *, domain_validator):
            note("verify-archive-hash")
            assert domain_validator(path, "local-recovery")["ok"] is True
            return Saved(baseline)

        @staticmethod
        def revalidate_saved_document_gui(exact_document, _saved):
            note("revalidate-saved-document")
            assert exact_document is document

    discarded = []
    result = lock_indicator._verified_local_save_and_clear(
        lease,
        Service(),
        document,
        save_service=Saver(),
        expectation_builder=lambda exact_document: (
            note("capture-expectations") or {"name": exact_document.Name}
        ),
        worker_validator=lambda *_args: note("worker-reopen") or {"ok": True},
        snapshot_discarder=lambda terminal: (
            note("discard-snapshot") or discarded.append(terminal)
        ),
        gui_dispatcher=Dispatcher(),
    )

    assert result["release"]["lease"]["state"] == "UNLOCKED_SAVED"
    assert [name for name, _thread in events] == [
        "get",
        "identity-1",
        "capture-expectations",
        "prepare-hash",
        "invoke-save",
        "verify-archive-hash",
        "worker-reopen",
        "identity-2",
        "revalidate-saved-document",
        "modified-read",
        "cas-clear",
        "discard-snapshot",
    ]
    by_name = dict(events)
    for off_gui_phase in (
        "get",
        "prepare-hash",
        "verify-archive-hash",
        "worker-reopen",
        "discard-snapshot",
    ):
        assert by_name[off_gui_phase] == caller_thread
        assert by_name[off_gui_phase] not in gui_threads
    for gui_phase in (
        "identity-1",
        "capture-expectations",
        "invoke-save",
        "identity-2",
        "revalidate-saved-document",
        "modified-read",
        "cas-clear",
    ):
        assert by_name[gui_phase] in gui_threads
        assert by_name[gui_phase] != caller_thread
    assert discarded == [result["release"]]


def test_local_save_verification_error_never_revalidates_or_cas_clears(tmp_path):
    path = str(tmp_path / "Part.FCStd")
    lease = _v2_record(state="USER_INTERVENED")
    lease["document"]["canonical_path"] = path
    lease["document"]["comparison_key"] = "part-comparison"
    baseline = FileBaseline(mtime_ns=1, size=2, sha256="c" * 64)
    lease["document_state"]["baseline"] = baseline.to_dict()
    events = []
    document = SimpleNamespace(Name="Part", Modified=False)

    class IdentityService:
        @staticmethod
        def inspect_registered_document(session_uuid, _document):
            events.append("identity")
            return SimpleNamespace(
                session_uuid=session_uuid,
                name="Part",
                canonical_path=path,
                comparison_key="part-comparison",
            )

    class Service:
        identity_service = IdentityService()

        @staticmethod
        def get(_selector):
            return lease

        @staticmethod
        def complete_local_save_and_clear(*_args, **_kwargs):
            events.append("cas-clear")
            raise AssertionError("CAS clear must not run after validation failure")

    class Saver:
        @staticmethod
        def prepare_save(*_args, **_kwargs):
            events.append("prepare")
            return "preflight"

        @staticmethod
        def invoke_save_gui(*_args):
            events.append("invoke")
            return SimpleNamespace(comparison_key="part-comparison")

        @staticmethod
        def verify_saved_file(*_args, **_kwargs):
            events.append("verify")
            raise RuntimeError("matching worker rejected Body.Tip")

        @staticmethod
        def revalidate_saved_document_gui(*_args):
            events.append("revalidate")

    dispatcher = SimpleNamespace(submit=lambda task, **_kwargs: task())
    with pytest.raises(RuntimeError, match="Body.Tip"):
        lock_indicator._verified_local_save_and_clear(
            lease,
            Service(),
            document,
            save_service=Saver(),
            expectation_builder=lambda _document: {},
            worker_validator=lambda *_args: {"ok": True},
            gui_dispatcher=dispatcher,
        )

    assert events == ["identity", "prepare", "invoke", "verify"]


@pytest.mark.parametrize("fails", [False, True])
def test_async_local_save_emits_completion_from_background_thread(monkeypatch, fails):
    caller_thread = threading.get_ident()
    emitted = []

    def pipeline(*_args, **_kwargs):
        if fails:
            raise RuntimeError("validation failed")
        return {"save": {"path": "Part.FCStd"}}

    monkeypatch.setattr(
        lock_indicator,
        "_verified_local_save_and_clear",
        pipeline,
    )
    worker = lock_indicator._start_verified_local_save_and_clear_async(
        {},
        object(),
        object(),
        completion_emit=lambda outcome: emitted.append(
            (threading.get_ident(), outcome)
        ),
    )
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(emitted) == 1
    completion_thread, outcome = emitted[0]
    assert completion_thread != caller_thread
    assert outcome["ok"] is (not fails)
    if fails:
        assert outcome["error_type"] == "RuntimeError"
        assert "validation failed" in outcome["error"]
    else:
        assert outcome["result"]["save"]["path"] == "Part.FCStd"


def test_local_save_completion_signal_is_explicitly_queued():
    queued = object()
    connections = []
    signal = SimpleNamespace(
        connect=lambda slot, connection: connections.append((slot, connection))
    )
    slot = object()
    qt_core = SimpleNamespace(
        Qt=SimpleNamespace(ConnectionType=SimpleNamespace(QueuedConnection=queued))
    )

    lock_indicator._connect_queued_qt_signal(signal, slot, qt_core)

    assert connections == [(slot, queued)]


def test_local_baseline_restore_runs_on_gui_and_preserves_session_and_lease(
    tmp_path,
):
    path = str(tmp_path / "Part.FCStd")
    snapshot_id = "16cd2790-0ae5-47d0-ad75-b463e665bf1a"
    lease = _v2_record(state="USER_INTERVENED")
    lease["document"]["canonical_path"] = path
    lease["document"]["comparison_key"] = "part-comparison"
    lease["document_state"]["snapshot_id"] = snapshot_id
    events = []
    gui_threads = []
    caller_thread = threading.get_ident()
    document = SimpleNamespace(Name="Part", FileName=path, Modified=True)

    def note(name):
        events.append((name, threading.get_ident()))

    class Dispatcher:
        @staticmethod
        def submit(task, *, timeout, request_id):
            assert timeout == lock_indicator._LOCAL_SAVE_GUI_TIMEOUT
            assert request_id.startswith("local-restore-")
            result = []
            failure = []

            def run():
                gui_threads.append(threading.get_ident())
                try:
                    result.append(task())
                except BaseException as exc:
                    failure.append(exc)

            thread = threading.Thread(target=run, name="mock-freecad-gui")
            thread.start()
            thread.join()
            if failure:
                raise failure[0]
            return result[0]

    identity_calls = 0

    class IdentityService:
        @staticmethod
        def inspect_registered_document(session_uuid, exact_document):
            nonlocal identity_calls
            assert session_uuid == "document-one"
            assert exact_document is document
            identity_calls += 1
            note(f"identity-{identity_calls}")
            return SimpleNamespace(
                session_uuid=session_uuid,
                name="Part",
                canonical_path=path,
                comparison_key="part-comparison",
                file_identity=None,
            )

    class Record:
        @staticmethod
        def to_public_dict():
            updated = dict(lease)
            updated["document_state"] = dict(lease["document_state"])
            updated["document_state"]["dirty"] = True
            return updated

    class Service:
        identity_service = IdentityService()

        @staticmethod
        def get(selector):
            note("get")
            assert selector == {"document_session_uuid": "document-one"}
            return lease

        @staticmethod
        def update_local_dirty(selector, *, dirty):
            note("persist-dirty")
            assert selector == {"document_session_uuid": "document-one"}
            assert dirty is True
            return Record()

    def resolve_snapshot(exact_snapshot_id):
        note("resolve-snapshot")
        assert exact_snapshot_id == snapshot_id
        return tmp_path / f"{snapshot_id}.FCStd"

    def restore_snapshot(
        exact_document,
        snapshot_path,
        *,
        expected_document_name,
        expected_source_path,
        validator,
    ):
        note("restore-in-place")
        assert exact_document is document
        assert snapshot_path.name == f"{snapshot_id}.FCStd"
        assert expected_document_name == "Part"
        assert expected_source_path == path
        assert validator(exact_document)["ok"] is True
        exact_document.Modified = True
        return {"ok": True, "dirty": True, "source_path": path}

    result = lock_indicator._restore_local_baseline(
        lease,
        Service(),
        document,
        gui_dispatcher=Dispatcher(),
        snapshot_path_resolver=resolve_snapshot,
        snapshot_restorer=restore_snapshot,
        document_validator=lambda exact_document: (
            note("validate-document") or {"ok": exact_document is document}
        ),
    )

    assert result["lease_preserved"] is True
    assert result["restored_id"] == snapshot_id
    assert result["document_session_uuid"] == "document-one"
    assert result["lease"]["lease_id"] == "lease-one"
    assert [name for name, _thread in events] == [
        "get",
        "get",
        "identity-1",
        "resolve-snapshot",
        "restore-in-place",
        "validate-document",
        "identity-2",
        "persist-dirty",
    ]
    assert events[0][1] == caller_thread
    for _name, thread_id in events[1:]:
        assert thread_id in gui_threads
        assert thread_id != caller_thread


def test_failed_in_place_restore_conservatively_persists_dirty(tmp_path):
    path = str(tmp_path / "Part.FCStd")
    snapshot_id = "16cd2790-0ae5-47d0-ad75-b463e665bf1a"
    lease = _v2_record(state="USER_INTERVENED")
    lease["document"]["canonical_path"] = path
    lease["document"]["comparison_key"] = "part-comparison"
    lease["document_state"]["snapshot_id"] = snapshot_id
    document = SimpleNamespace(Name="Part", FileName=path, Modified=False)
    dirty_updates = []

    identity = SimpleNamespace(
        session_uuid="document-one",
        name="Part",
        canonical_path=path,
        comparison_key="part-comparison",
        file_identity=None,
    )
    service = SimpleNamespace(
        identity_service=SimpleNamespace(
            inspect_registered_document=lambda *_args: identity
        ),
        get=lambda _selector: lease,
        update_local_dirty=lambda selector, *, dirty: dirty_updates.append(
            (selector, dirty)
        ),
    )
    dispatcher = SimpleNamespace(submit=lambda task, **_kwargs: task())

    def partially_fail(*_args, **_kwargs):
        document.Modified = False
        raise RuntimeError("snapshot load was partial")

    with pytest.raises(RuntimeError, match="partial"):
        lock_indicator._restore_local_baseline(
            lease,
            service,
            document,
            gui_dispatcher=dispatcher,
            snapshot_path_resolver=lambda _snapshot_id: tmp_path / "snapshot.FCStd",
            snapshot_restorer=partially_fail,
            document_validator=lambda _document: {"ok": True},
        )

    assert dirty_updates == [({"document_session_uuid": "document-one"}, True)]
    assert lease["lease_id"] == "lease-one"
    assert lease["document"]["session_uuid"] == "document-one"


@pytest.mark.parametrize("fails", [False, True])
def test_async_baseline_restore_emits_one_background_outcome(monkeypatch, fails):
    caller_thread = threading.get_ident()
    emitted = []

    def restore(*_args, **_kwargs):
        if fails:
            raise RuntimeError("restore rejected")
        return {"lease_preserved": True}

    monkeypatch.setattr(lock_indicator, "_restore_local_baseline", restore)
    worker = lock_indicator._start_local_baseline_restore_async(
        {},
        object(),
        object(),
        completion_emit=lambda outcome: emitted.append(
            (threading.get_ident(), outcome)
        ),
    )
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(emitted) == 1
    assert emitted[0][0] != caller_thread
    assert emitted[0][1]["ok"] is (not fails)
