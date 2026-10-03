"""B4 – GUI-thread collaboration API must use commitCompatibilityMutationAsync.

Unit tests verify that when the caller is the FreeCAD GUI thread:
- ``commitCompatibilityMutation`` (sync, blocking) is never invoked.
- ``commitCompatibilityMutationAsync`` is invoked instead.
- The returned :class:`_AsyncMutationWaiter` calls the handle's ``wait()``
  callable and returns the *actual* commit result (same fields the sync path
  returns: ``operation_id``, ``message``, ``conflicts``, ``published_revisions``).
- Callback / postcondition failures propagate as proven-rejection dicts or
  re-raised exceptions — identical to the non-GUI sync path.

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


# A distinctive sentinel result that the fake async method will surface.
# Tests assert the *exact same object* is delivered by the waiter — not a
# synthetic {"status": "Committed", "committed": True} copy.
_SENTINEL_RESULT = {
    "status": "Committed",
    "committed": True,
    "operation_id": "test-op-42",
    "message": "sentinel commit",
    "conflicts": [],
    "published_revisions": [7],
}


class _FakeAsyncBodyDoc:
    """Document fake exposing both the sync and async mutation surfaces.

    ``commitCompatibilityMutationAsync`` runs the callbacks immediately
    (simulating the owner thread) and returns a handle dict with a real
    ``wait()`` callable — matching what the fixed C++ binding returns.
    ``commitCompatibilityMutation`` is present but must not be called on
    the GUI thread.
    """

    def __init__(self, result: object = None) -> None:
        self.Name = "TestDoc"
        self.result = result if result is not None else dict(_SENTINEL_RESULT)
        self.sync_calls: list[tuple[Any, dict[str, Any]]] = []
        self.async_calls: list[tuple[Any, dict[str, Any]]] = []

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
        """Async variant – run callbacks immediately; return handle with wait()."""
        self.async_calls.append((callback, dict(kwargs)))
        # Simulate the owner thread running the mutation synchronously.
        captured_exc: BaseException | None = None
        try:
            callback()
            pc = kwargs.get("postcondition")
            if callable(pc):
                pc()
        except BaseException as exc:  # noqa: BLE001
            captured_exc = exc

        result = self.result

        def _wait(timeout: float = 60.0) -> object:
            if captured_exc is not None:
                raise captured_exc
            return result

        return {"state": "Running", "wait": _wait}


# ---------------------------------------------------------------------------
# Test: commit_body_create_mutation
# ---------------------------------------------------------------------------


def test_body_create_uses_async_on_gui_thread(monkeypatch) -> None:
    """Async variant must be called; sync variant must not be touched."""
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

    # Sync must not have been touched.
    assert doc.sync_calls == [], "commitCompatibilityMutation must not be called on GUI thread"
    assert len(doc.async_calls) == 1, "commitCompatibilityMutationAsync must be called"

    # Callbacks ran inside the fake's async (simulating owner thread).
    assert applied == [doc], "callback must have been called with the document"
    assert postcondition_called == [True]

    # Waiter returns the actual result dict — not a synthetic copy.
    result = waiter.await_result(timeout=5.0)
    assert result is doc.result, "waiter must return the actual native result object"
    assert result.get("operation_id") == "test-op-42"
    assert result.get("published_revisions") == [7]


def test_body_create_sync_path_on_non_gui_thread(monkeypatch) -> None:
    """Sync path is used directly when NOT on the GUI thread."""
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: False)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    result = api.commit_body_create_mutation(
        "TestDoc", lambda d: None, lambda d: True
    )

    assert doc.sync_calls, "commitCompatibilityMutation must be called off GUI thread"
    assert doc.async_calls == [], "async variant must not be called off GUI thread"
    assert result is doc.result, "sync path must return the actual native result"


def test_body_create_callback_raises_returns_proven_rejection(monkeypatch) -> None:
    """Callback exception from async path → proven-rejection dict via waiter."""
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)

    class _ApplyError(Exception):
        pass

    def bad_callback(d):
        raise _ApplyError("apply failed")

    # The fake's async method raises the exception from wait().
    # _AsyncMutationWaiter.await_result() catches it, calls proven_rejection,
    # and returns the rejection dict.
    waiter = api.commit_body_create_mutation("TestDoc", bad_callback, lambda d: True)
    result = waiter.await_result(timeout=5.0)

    assert isinstance(result, dict), "proven rejection must be returned as dict"
    assert result.get("status") == "ApplyFailed"
    assert result.get("committed") is False
    assert result.get("rollback_succeeded") is True
    assert "apply failed" in result.get("message", "")


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
    assert applied == [doc]

    result = waiter.await_result(timeout=5.0)
    assert result is doc.result
    assert result.get("operation_id") == "test-op-42"


def test_native_mutation_callback_raises_proven_rejection(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)

    class _NativeError(Exception):
        pass

    def bad_callback(d):
        raise _NativeError("native failed")

    waiter = api.commit_native_mutation("TestDoc", bad_callback, lambda d: True)
    result = waiter.await_result(timeout=5.0)

    assert result.get("status") == "ApplyFailed"
    assert result.get("committed") is False
    assert result.get("rollback_succeeded") is True


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
    assert called == [True], "callback must have been called (by fake owner thread)"

    result = waiter.await_result(timeout=5.0)
    assert result is doc.result
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
    assert callback_ran == [True]
    assert postcondition_ran == [True]

    result = waiter.await_result(timeout=5.0)
    assert result is doc.result


def test_compat_mutation_callback_raises_reraises(monkeypatch) -> None:
    """Callback exception from compat path re-raises (no proven_rejection)."""
    mod = _load_module()
    doc = _FakeAsyncBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)

    class _CompatError(Exception):
        pass

    def bad_callback():
        raise _CompatError("compat failed")

    waiter = api.commit_compatibility_mutation("TestDoc", bad_callback)

    with pytest.raises(_CompatError, match="compat failed"):
        waiter.await_result(timeout=5.0)


# ---------------------------------------------------------------------------
# Test: no async binding raises
# ---------------------------------------------------------------------------


def test_no_async_binding_on_gui_thread_raises(monkeypatch) -> None:
    """When commitCompatibilityMutationAsync is absent, GUI-thread raises RuntimeError."""
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


# ---------------------------------------------------------------------------
# Test: handle without wait() raises
# ---------------------------------------------------------------------------


def test_handle_missing_wait_raises(monkeypatch) -> None:
    """If the handle has no wait(), _commit_async_on_gui_thread raises RuntimeError."""
    mod = _load_module()

    class _BadAsyncDoc:
        Name = "BadAsync"

        def getObject(self, name):
            return None

        def addObject(self, t, n):
            return object()

        def commitCompatibilityMutation(self, cb, **kw):
            cb()
            return {"status": "Committed", "committed": True}

        def commitCompatibilityMutationAsync(self, cb, **kw):
            # Returns handle without a wait() callable (old stub).
            return {"state": "Running"}

    doc = _BadAsyncDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    with pytest.raises(RuntimeError, match="wait\\(\\)"):
        api.commit_body_create_mutation("BadAsync", lambda d: None, lambda d: True)


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

    # Await result from a dedicated background thread (simulating the RPC thread).
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

    assert not rpc_error, f"await_result raised: {rpc_error[0]}"
    assert rpc_result, "await_result must return a result"
    assert rpc_result[0] is doc.result, "RPC thread must receive actual native result"
    assert rpc_result[0].get("operation_id") == "test-op-42"
