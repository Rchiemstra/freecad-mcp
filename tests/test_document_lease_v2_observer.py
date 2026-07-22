from __future__ import annotations

import sys
import types
from pathlib import Path

import FreeCADGui
import pytest

from addon.FreeCADMCP.document_lease import observer as observer_mod


class FakeDocument:
    def __init__(self, name="Model", filename="", modified=True):
        self.Name = name
        self.FileName = filename
        self.Modified = modified


class FakeIdentity:
    def __init__(self, document: FakeDocument):
        self.session_uuid = "doc-session"
        self.name = document.Name
        self.canonical_path = document.FileName or None


class FakeIdentityService:
    def __init__(self, document: FakeDocument):
        self.document = document
        self.identity = FakeIdentity(document)

    def resolve(self, selector):
        name = selector.get("document_name")
        path = selector.get("canonical_path")
        session_uuid = selector.get("document_session_uuid")
        if name and name != self.document.Name:
            raise LookupError(name)
        if path and Path(path).resolve() != Path(self.document.FileName).resolve():
            raise LookupError(path)
        if session_uuid and session_uuid != self.identity.session_uuid:
            raise LookupError(session_uuid)
        return self.identity


class FakeService:
    def __init__(self, document: FakeDocument):
        self.identity_service = FakeIdentityService(document)
        self.current = {"state": "LOCKED_IDLE", "generation": 7}
        self.takeovers = []
        self.dirty_updates = []
        self.sidecar_delete_calls = []

    def get(self, selector):
        if selector != "doc-session":
            raise LookupError(selector)
        return self.current

    def takeover(self, selector, *, dirty, reason):
        self.takeovers.append({"selector": selector, "dirty": dirty, "reason": reason})
        self.current = {"state": "USER_INTERVENED", "generation": 8}
        return self.current

    def update_local_dirty(self, selector, *, dirty):
        self.dirty_updates.append((selector, dirty))
        self.current = {**self.current, "dirty": dirty}
        return self.current


def make_observer(document, *, checker=lambda _key: False):
    service = FakeService(document)
    queued = []
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: service,
        agent_mutation_checker=checker,
        selected_document_provider=lambda: document,
        notification_callback=delivered.append,
        notification_queue=queued.append,
    )
    return observer, service, queued, delivered


def test_property_change_fences_owner_and_queues_redacted_notification(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, delivered = make_observer(document)
    obj = types.SimpleNamespace(Document=document)

    result = observer.slotChangedObject(obj, "Placement")

    assert result == {"state": "USER_INTERVENED", "generation": 8}
    assert service.takeovers == [
        {
            "selector": "doc-session",
            "dirty": True,
            "reason": "Unscoped FreeCAD object property change detected: Placement",
        }
    ]
    assert delivered == []
    assert len(queued) == 1

    queued.pop()()
    assert delivered[0] == observer_mod.LeaseObserverEvent(
        kind="object property change",
        document_name="Model",
        document_session_uuid="doc-session",
        canonical_path=str(tmp_path / "Model.FCStd"),
        reason="Unscoped FreeCAD object property change detected: Placement",
        dirty=True,
        state="USER_INTERVENED",
        generation=8,
    )
    assert not hasattr(delivered[0], "token")


def test_unknown_gui_modified_state_is_fenced_as_dirty(
    tmp_path, monkeypatch
):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"))
    del document.Modified
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    observer, service, _queued, _delivered = make_observer(document)

    observer.slotChangedObject(
        types.SimpleNamespace(Document=document), "Placement"
    )

    assert service.takeovers[0]["dirty"] is True


@pytest.mark.parametrize("attributed_key", ["Model", "resolved-path"])
def test_agent_attribution_accepts_document_name_and_resolved_path(
    tmp_path, attributed_key
):
    filename = tmp_path / "Model.FCStd"
    document = FakeDocument("Model", str(filename), modified=True)
    resolved = str(filename.resolve())

    def checker(key):
        if attributed_key == "Model":
            return key == "Model"
        return key == resolved

    observer, service, queued, _delivered = make_observer(document, checker=checker)

    assert observer.slotCreatedObject(types.SimpleNamespace(Document=document)) is None
    assert service.takeovers == []
    assert queued == []


@pytest.mark.parametrize(
    ("callback", "args", "kind"),
    [
        (
            "slotCreatedObject",
            lambda d: (types.SimpleNamespace(Document=d),),
            "object creation",
        ),
        (
            "slotDeletedObject",
            lambda d: (types.SimpleNamespace(Document=d),),
            "object deletion",
        ),
        (
            "slotAppendDynamicProperty",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "dynamic property addition",
        ),
        (
            "slotRemoveDynamicProperty",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "dynamic property removal",
        ),
        (
            "slotChangePropertyEditor",
            lambda d: (types.SimpleNamespace(Document=d), "CustomLength"),
            "property editor change",
        ),
        (
            "slotBeforeAddingDynamicExtension",
            lambda d: (types.SimpleNamespace(Document=d), "App::LinkExtension"),
            "dynamic extension addition",
        ),
        (
            "slotAddedDynamicExtension",
            lambda d: (types.SimpleNamespace(Document=d), "App::LinkExtension"),
            "dynamic extension addition",
        ),
        ("slotUndoDocument", lambda d: (d,), "undo"),
        ("slotRedoDocument", lambda d: (d,), "redo"),
        ("slotBeforeRecomputeDocument", lambda d: (d,), "recompute"),
        ("slotRecomputedDocument", lambda d: (d,), "recompute"),
        ("slotOpenTransaction", lambda d: (d, "Edit sketch"), "transaction open"),
        ("slotCommitTransaction", lambda d: (d,), "transaction commit"),
        ("slotAbortTransaction", lambda d: (d,), "transaction abort"),
        ("slotStartSaveDocument", lambda d: (d, d.FileName), "save"),
        ("slotFinishSaveDocument", lambda d: (d, d.FileName), "save"),
        ("slotDeletedDocument", lambda d: (d,), "document close"),
    ],
)
def test_supported_app_callbacks_fence_unscoped_changes(tmp_path, callback, args, kind):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)

    getattr(observer, callback)(*args(document))

    assert len(service.takeovers) == 1
    assert kind in service.takeovers[0]["reason"]
    assert len(queued) == 1


def test_gui_edit_mode_resolves_view_provider_object(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=False)
    observer, service, queued, _delivered = make_observer(document)
    gui_observer = observer_mod.LeaseGuiObserver(observer)
    view_provider = types.SimpleNamespace(
        Object=types.SimpleNamespace(Document=document)
    )

    gui_observer.slotInEdit(view_provider)

    assert service.takeovers[0]["dirty"] is False
    assert "GUI edit-mode entry" in service.takeovers[0]["reason"]
    assert len(queued) == 1


def test_close_callback_fences_without_sidecar_cleanup(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, _queued, _delivered = make_observer(document)

    observer.slotDeletedDocument(document)

    assert service.current["state"] == "USER_INTERVENED"
    assert service.sidecar_delete_calls == []


def test_repeated_callbacks_do_not_repeat_takeover_for_intervened_state(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)
    obj = types.SimpleNamespace(Document=document)

    observer.slotBeforeChangeObject(obj, "Length")
    observer.slotChangedObject(obj, "Length")
    observer.slotRecomputedDocument(document)

    assert len(service.takeovers) == 1
    assert len(queued) == 1


def test_intervened_document_observer_refreshes_dirty_without_new_takeover(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, queued, _delivered = make_observer(document)
    observer.take_over_selected_document(reason="Confirmed")
    document.Modified = False

    result = observer.slotFinishSaveDocument(document, document.FileName)

    assert result["state"] == "USER_INTERVENED"
    assert result["dirty"] is False
    assert service.dirty_updates[-1] == ("doc-session", False)
    assert len(service.takeovers) == 1
    assert len(queued) == 1


def test_manual_takeover_uses_selected_document_even_during_agent_context(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    observer, service, _queued, _delivered = make_observer(
        document, checker=lambda _key: True
    )

    observer.take_over_selected_document(reason="Confirmed by local user")

    assert len(service.takeovers) == 1
    assert "manual takeover" in service.takeovers[0]["reason"]
    assert "Confirmed by local user" in service.takeovers[0]["reason"]


def test_created_document_freshly_registers_and_imports_adjacent_v2(tmp_path):
    model = tmp_path / "Recovered.FCStd"
    model.write_bytes(b"archive")
    sidecar = Path(f"{model}.freecad-mcp.lock")
    sidecar.write_bytes(b"opaque-valid-record-owned-by-service")
    document = FakeDocument("Recovered", str(model), modified=True)
    identity = types.SimpleNamespace(
        session_uuid="local-session",
        name="Recovered",
        canonical_path=str(model),
    )
    calls = []

    class Identities:
        @staticmethod
        def register_document(exact):
            assert exact is document
            calls.append("register")
            return identity

        @staticmethod
        def inspect_registered_document(session_uuid, exact):
            assert session_uuid == "local-session"
            assert exact is document
            calls.append("inspect")
            return identity

    class Service:
        identity_service = Identities()

        @staticmethod
        def get(_selector):
            return None

        @staticmethod
        def get_foreign_recovery(_selector):
            return None

        @staticmethod
        def import_adjacent_foreign_recovery(selector, *, live_document):
            calls.append(("import", selector, live_document))
            return {
                "generation": 4,
                "lease": {"state": "STALE"},
                "source": "foreign_recovery",
            }

    queued = []
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: Service(),
        notification_callback=delivered.append,
        notification_queue=queued.append,
    )

    result = observer.slotCreatedDocument(document)

    assert result["source"] == "foreign_recovery"
    assert calls == [
        "register",
        "inspect",
        ("import", "local-session", identity),
    ]
    assert len(queued) == 1
    queued[0]()
    assert delivered[0].state == "STALE"
    assert delivered[0].document_session_uuid == "local-session"


def test_created_document_never_clears_or_recovers_invalid_sidecar(tmp_path):
    model = tmp_path / "Malformed.FCStd"
    model.write_bytes(b"archive")
    sidecar = Path(f"{model}.freecad-mcp.lock")
    original = b"malformed authority"
    sidecar.write_bytes(original)
    document = FakeDocument("Malformed", str(model), modified=False)
    identity = types.SimpleNamespace(
        session_uuid="local-session",
        name="Malformed",
        canonical_path=str(model),
    )

    class Identities:
        register_document = staticmethod(lambda _document: identity)
        inspect_registered_document = staticmethod(
            lambda _session_uuid, _document: identity
        )

    service = types.SimpleNamespace(
        identity_service=Identities(),
        get=lambda _selector: None,
        get_foreign_recovery=lambda _selector: None,
        import_adjacent_foreign_recovery=lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(ValueError("invalid schema")),
    )
    observer = observer_mod.LeaseObserver(service_provider=lambda: service)

    assert observer.slotCreatedDocument(document) is None
    assert sidecar.read_bytes() == original


def test_missing_or_failing_runtime_service_is_safe(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    no_service = observer_mod.LeaseObserver(service_provider=lambda: None)
    bad_service = observer_mod.LeaseObserver(
        service_provider=lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    )

    assert no_service.slotRecomputedDocument(document) is None
    assert bad_service.slotRecomputedDocument(document) is None


def test_default_service_lookup_uses_loaded_module_without_import(monkeypatch):
    service = object()
    module = types.SimpleNamespace(document_lease_service=service)
    monkeypatch.setitem(sys.modules, "rpc_server.rpc_server", module)

    assert observer_mod.get_runtime_service() is service


class FakeObserverModule:
    def __init__(self):
        self.added = []
        self.removed = []

    def addDocumentObserver(self, value):
        self.added.append(value)

    def removeDocumentObserver(self, value):
        self.removed.append(value)


def test_registration_and_unregistration_are_idempotent():
    observer_mod.unregister_observer()
    app = FakeObserverModule()
    gui = FakeObserverModule()
    try:
        first = observer_mod.register_observer(
            freecad_module=app,
            freecad_gui_module=gui,
            service_provider=lambda: None,
        )
        second = observer_mod.register_observer(
            freecad_module=app,
            freecad_gui_module=gui,
            service_provider=lambda: None,
        )

        assert first is second
        assert app.added == [first]
        assert len(gui.added) == 1
        assert app._mcp_document_lease_observer is first
    finally:
        observer_mod.unregister_observer()

    assert app.removed == [first]
    assert gui.removed == gui.added
    assert not hasattr(app, "_mcp_document_lease_observer")
    assert not hasattr(gui, "_mcp_document_lease_gui_observer")


def test_notification_queue_failure_does_not_deliver_synchronously(tmp_path):
    document = FakeDocument("Model", str(tmp_path / "Model.FCStd"), modified=True)
    service = FakeService(document)
    delivered = []
    observer = observer_mod.LeaseObserver(
        service_provider=lambda: service,
        notification_callback=delivered.append,
        notification_queue=lambda _callback: (_ for _ in ()).throw(
            RuntimeError("Qt stopped")
        ),
    )

    observer.slotRecomputedDocument(document)

    assert service.current["state"] == "USER_INTERVENED"
    assert delivered == []


def test_register_live_document_recovery_skips_name_resolve_mismatch():
    """Registration failure must not resolve-by-name into a foreign proxy."""

    from addon.FreeCADMCP.document_lease.identity import (
        DocumentIdentityService,
        DuplicateDocumentError,
    )

    identities = DocumentIdentityService()
    first = FakeDocument("Model", filename=r"C:\tmp\Model.FCStd")
    second = FakeDocument("Model", filename=r"C:\tmp\Model.FCStd")
    identities.register_document(first)

    class _Service:
        identity_service = identities

        def get(self, _session):
            return None

    # Same name, different proxy object → register raises; recovery must skip
    # quietly instead of inspect-mismatch warning spam.
    with pytest.raises(DuplicateDocumentError):
        identities.register_document(second)

    identity, imported = observer_mod.register_live_document_recovery(
        _Service(), second
    )
    assert identity is None
    assert imported is None
