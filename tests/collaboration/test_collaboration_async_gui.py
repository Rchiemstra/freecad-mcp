"""B4 – GUI-thread collaboration API must use commitCompatibilityMutationAsync.

Unit tests verify that when the caller is the FreeCAD GUI thread:
- ``commitCompatibilityMutation`` (sync, blocking) is never invoked.
- ``commitCompatibilityMutationAsync`` is invoked instead.
- The returned :class:`_AsyncMutationWaiter` resolves off the GUI thread.

All three commit entry-points are covered:
    * ``commit_body_create_mutation``
    * ``commit_native_mutation``
    * ``commit_compatibility_mutation``
"""

from __future__ import annotations

import importlib
import threading
from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_module():
    return importlib.import_module("addon.FreeCADMCP.collaboration_api")


class _FakeAsyncBodyDoc:
    """Document fake that exposes both sync and async mutation surfaces."""

    def __init__(self, result: object = None) -> None:
        self.Name = "TestDoc"
        self.result = result or {"status": "Committed", "committed": True}
        self.sync_calls: list[tuple[Any, dict[str, Any]]] = []
        self.async_calls: list[tuple[Any, dict[str, Any]]] = []
        self._pending_callback: Any = None
        self._pending_postcondition: Any = None

    # --- _NativeBodyDocument protocol ---

    def getObject(self, name: str) -> object:
        return None

    def addObject(self, object_type: str, name: str) -> object:
        return object()

    def commitCompatibilityMutation(self, callback, **kwargs):
        """Sync variant – must NOT be called on the GUI thread."""
        self.sync_calls.append((callback, dict(kwargs)))
        callback()
        pc = kwargs.get("postcondition")
        if callable(pc):
            pc()
        return self.result

    def commitCompatibilityMutationAsync(self, callback, **kwargs):
        """Async variant – stores the callbacks for deferred triggering."""
        self.async_calls.append((callback, dict(kwargs)))
        self._pending_callback = callback
        self._pending_postcondition = kwargs.get("postcondition")
        # Return a minimal handle dict (the real C++ returns a capsule dict).
        return {"state": "Running"}

    def trigger(self) -> None:
        """Simulate the owner thread executing the pending mutation."""
        if self._pending_callback is not None:
            self._pending_callback()
        if callable(self._pending_postcondition):
            self._pending_postcondition()
        self._pending_callback = None
        self._pending_postcondition = None


# ---------------------------------------------------------------------------
# Test: commit_body_create_mutation
# ---------------------------------------------------------------------------


def test_body_create_uses_async_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    applied: list[object] = []
    postcondition_called: list[bool] = []

    def callback(d):
        applied.append(d)

    def postcondition(d):
        postcondition_called.append(True)
        return True

    waiter = api.commit_body_create_mutation("TestDoc", callback, postcondition)

    # Sync method must not have been touched.
    assert doc.sync_calls == [], "commitCompatibilityMutation must not be called on GUI thread"
    assert len(doc.async_calls) == 1, "commitCompatibilityMutationAsync must be called"
    assert applied == [], "callback must not run before trigger()"

    # Simulate owner thread completing the mutation.
    doc.trigger()
    assert applied == [doc], "callback must receive the document"
    assert postcondition_called == [True]

    # Await the result off the GUI thread (event already set by trigger).
    result = waiter.await_result(timeout=5.0)
    assert isinstance(result, dict)
    assert result.get("status") == "Committed"
    assert result.get("committed") is True


def test_body_create_sync_path_on_non_gui_thread(monkeypatch) -> None:
    """Sync path is used when NOT on the GUI thread."""
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: False)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    result = api.commit_body_create_mutation(
        "TestDoc", lambda d: None, lambda d: True
    )

    assert doc.sync_calls, "commitCompatibilityMutation must be called off GUI thread"
    assert doc.async_calls == [], "async variant must not be called off GUI thread"
    assert result.get("committed") is True


# ---------------------------------------------------------------------------
# Test: commit_native_mutation
# ---------------------------------------------------------------------------


def test_native_mutation_uses_async_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    applied: list[object] = []

    def callback(d):
        applied.append(d)
        return True

    def postcondition(d):
        return True

    waiter = api.commit_native_mutation("TestDoc", callback, postcondition)

    assert doc.sync_calls == [], "sync variant must not be called on GUI thread"
    assert len(doc.async_calls) == 1

    doc.trigger()
    assert applied == [doc]

    result = waiter.await_result(timeout=5.0)
    assert result.get("status") == "Committed"
    assert result.get("committed") is True


# ---------------------------------------------------------------------------
# Test: commit_compatibility_mutation
# ---------------------------------------------------------------------------


def test_compat_mutation_uses_async_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    called: list[bool] = []
    callback = lambda: called.append(True)  # noqa: E731

    waiter = api.commit_compatibility_mutation("TestDoc", callback)

    assert doc.sync_calls == [], "sync variant must not be called on GUI thread"
    assert len(doc.async_calls) == 1
    assert called == [], "callback must not run before trigger()"

    doc.trigger()
    assert called == [True]

    result = waiter.await_result(timeout=5.0)
    assert result.get("status") == "Committed"


def test_compat_mutation_with_postcondition_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    callback_ran: list[bool] = []
    postcondition_ran: list[bool] = []

    waiter = api.commit_compatibility_mutation(
        "TestDoc",
        lambda: callback_ran.append(True),
        postcondition=lambda: postcondition_ran.append(True) or True,
    )

    assert doc.sync_calls == []
    assert doc.async_calls

    doc.trigger()
    assert callback_ran == [True]
    # postcondition wrapped by signaling_postcondition; may be called inside trigger
    result = waiter.await_result(timeout=5.0)
    assert result.get("committed") is True


# ---------------------------------------------------------------------------
# Test: await off the GUI thread via a real background thread
# ---------------------------------------------------------------------------


def test_await_result_off_gui_thread(monkeypatch) -> None:
    """The awaiter must be safe to call from a non-GUI background thread."""
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    waiter = api.commit_body_create_mutation(
        "TestDoc", lambda d: None, lambda d: True
    )

    # Trigger from a background thread (simulating the owner thread).
    def _owner_thread():
        import time
        time.sleep(0.02)
        doc.trigger()

    owner = threading.Thread(target=_owner_thread, daemon=True)
    owner.start()

    # Await result from another background thread (simulating the RPC thread).
    rpc_result: list[Any] = []
    rpc_error: list[BaseException] = []

    def _rpc_thread():
        try:
            rpc_result.append(waiter.await_result(timeout=5.0))
        except BaseException as exc:  # noqa: BLE001
            rpc_error.append(exc)

    rpc = threading.Thread(target=_rpc_thread, daemon=True)
    rpc.start()
    rpc.join(timeout=6.0)
    owner.join(timeout=1.0)

    assert not rpc_error, f"await_result raised: {rpc_error[0]}"
    assert rpc_result, "await_result must return a result"
    assert rpc_result[0].get("status") == "Committed"


def test_no_async_binding_on_gui_thread_raises(monkeypatch) -> None:
    """When commitCompatibilityMutationAsync is absent, GUI-thread raises."""
    mod = _load_module()

    class _SyncOnlyDoc:
        Name = "SyncOnly"

        def getObject(self, name):
            return None

        def addObject(self, t, n):
            return object()

        def commitCompatibilityMutation(self, cb, **kw):
            return {"status": "Committed", "committed": True}

    doc = _SyncOnlyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    with pytest.raises(RuntimeError, match="commitCompatibilityMutationAsync"):
        api.commit_body_create_mutation("SyncOnly", lambda d: None, lambda d: True)
