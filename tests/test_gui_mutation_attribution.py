from __future__ import annotations

import threading
import types

from addon.FreeCADMCP import document_lock
from addon.FreeCADMCP.document_lease.observer import LeaseObserver


def _clear_context() -> None:
    document_lock.reset_registry_for_tests()


def test_exact_request_scope_is_reference_counted_for_safe_nesting():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"
    scope = ("document-session", "Model")

    assert document_lock.begin_agent_mutation_scope(request_id, scope) is True
    assert document_lock.begin_agent_mutation_scope(
        request_id, tuple(reversed(scope))
    ) is True
    assert document_lock.is_agent_mutating(
        "document-session", request_id=request_id
    )
    assert not document_lock.is_agent_mutating("undeclared", request_id=request_id)
    assert not document_lock.is_agent_mutating(
        "document-session", request_id="22222222-2222-4222-8222-222222222222"
    )
    assert document_lock.get_agent_mutation_context() == {
        "active": True,
        "request_id": request_id,
        "document_keys": ("Model", "document-session"),
        "depth": 2,
        "valid": True,
        "violation": None,
        "thread_id": threading.get_ident(),
        "legacy": False,
    }

    assert document_lock.end_agent_mutation_scope(request_id, scope) is True
    assert document_lock.is_agent_mutating("Model", request_id=request_id)
    assert document_lock.end_agent_mutation_scope(request_id, scope) is True
    assert document_lock.get_agent_mutation_context()["active"] is False


def test_nested_different_request_poisons_outer_scope_until_full_unwind():
    _clear_context()
    outer = "11111111-1111-4111-8111-111111111111"
    nested = "22222222-2222-4222-8222-222222222222"
    scope = ("document-session",)

    assert document_lock.begin_agent_mutation_scope(outer, scope) is True
    assert document_lock.begin_agent_mutation_scope(nested, scope) is False
    context = document_lock.get_agent_mutation_context()
    assert context["valid"] is False
    assert "mismatch" in context["violation"]
    assert not document_lock.is_agent_mutating("document-session")

    assert document_lock.end_agent_mutation_scope(nested, scope) is False
    assert not document_lock.is_agent_mutating("document-session")
    assert document_lock.end_agent_mutation_scope(outer, scope) is False
    assert document_lock.get_agent_mutation_context()["active"] is False


def test_nested_changed_document_scope_is_not_agent_attributed():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"

    document_lock.begin_agent_mutation_scope(request_id, ("document-a",))
    assert not document_lock.begin_agent_mutation_scope(
        request_id, ("document-a", "document-b")
    )
    assert not document_lock.is_agent_mutating("document-a", request_id=request_id)
    assert not document_lock.is_agent_mutating("document-b", request_id=request_id)
    document_lock.end_agent_mutation_scope(
        request_id, ("document-a", "document-b")
    )
    document_lock.end_agent_mutation_scope(request_id, ("document-a",))


def test_request_attribution_is_visible_only_on_its_executing_thread():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"
    entered = threading.Event()
    release = threading.Event()
    worker_result = []

    def worker():
        document_lock.begin_agent_mutation_scope(request_id, ("document-session",))
        worker_result.append(document_lock.is_agent_mutating("document-session"))
        entered.set()
        release.wait(timeout=5)
        document_lock.end_agent_mutation_scope(request_id, ("document-session",))

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=5)
    assert not document_lock.is_agent_mutating("document-session")
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert worker_result == [True]


def test_legacy_per_key_facade_remains_thread_local_and_reference_counted():
    _clear_context()
    document_lock.begin_agent_mutation("Model")
    document_lock.begin_agent_mutation("Model")
    document_lock.begin_agent_mutation("other")

    assert document_lock.is_agent_mutating("Model")
    assert document_lock.get_agent_mutation_context()["legacy"] is True
    document_lock.end_agent_mutation("Model")
    assert document_lock.is_agent_mutating("Model")
    document_lock.end_agent_mutation("Model")
    assert not document_lock.is_agent_mutating("Model")
    assert document_lock.is_agent_mutating("other")
    document_lock.end_agent_mutation("other")
    assert document_lock.get_agent_mutation_context()["active"] is False


class _Document:
    Name = "Model"
    FileName = ""
    Modified = True


class _IdentityService:
    identity = types.SimpleNamespace(
        session_uuid="document-session",
        name="Model",
        canonical_path=None,
        comparison_key=None,
    )

    def resolve(self, selector):
        if selector.get("document_name") not in {None, "Model"}:
            raise LookupError(selector)
        return self.identity


class _LeaseService:
    identity_service = _IdentityService()

    def __init__(self):
        self.current = {"state": "LOCKED_IDLE", "generation": 4}
        self.takeovers = []

    def get(self, selector):
        assert selector == "document-session"
        return self.current

    def takeover(self, selector, *, dirty, reason):
        self.takeovers.append((selector, dirty, reason))
        self.current = {"state": "USER_INTERVENED", "generation": 5}
        return self.current


def _observer(service):
    return LeaseObserver(
        service_provider=lambda: service,
        notification_queue=lambda callback: callback(),
    )


def test_observer_accepts_only_exact_active_request_document_scope():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"
    service = _LeaseService()
    observer = _observer(service)
    subject = types.SimpleNamespace(Document=_Document())

    document_lock.begin_agent_mutation_scope(request_id, ("document-session",))
    try:
        assert observer.slotCreatedObject(subject) is None
    finally:
        document_lock.end_agent_mutation_scope(request_id, ("document-session",))
    assert service.takeovers == []


def test_observer_fences_undeclared_document_during_active_request():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"
    service = _LeaseService()
    observer = _observer(service)
    subject = types.SimpleNamespace(Document=_Document())

    document_lock.begin_agent_mutation_scope(request_id, ("different-document",))
    try:
        result = observer.slotChangedObject(subject, "Placement")
    finally:
        document_lock.end_agent_mutation_scope(request_id, ("different-document",))

    assert result["state"] == "USER_INTERVENED"
    assert service.takeovers[0][0] == "document-session"
    assert "Unscoped FreeCAD object property change" in service.takeovers[0][2]


def test_observer_fences_change_while_nested_request_mismatches():
    _clear_context()
    request_id = "11111111-1111-4111-8111-111111111111"
    other_request = "22222222-2222-4222-8222-222222222222"
    scope = ("document-session",)
    service = _LeaseService()
    observer = _observer(service)

    document_lock.begin_agent_mutation_scope(request_id, scope)
    document_lock.begin_agent_mutation_scope(other_request, scope)
    try:
        result = observer.slotCreatedObject(
            types.SimpleNamespace(Document=_Document())
        )
    finally:
        document_lock.end_agent_mutation_scope(other_request, scope)
        document_lock.end_agent_mutation_scope(request_id, scope)

    assert result["state"] == "USER_INTERVENED"
    assert len(service.takeovers) == 1

