"""B4 – GUI-thread collaboration API must offload sync mutation to background.

Unit tests verify that when the caller is the FreeCAD GUI thread:
- ``commitCompatibilityMutation`` (sync) is called from a *background* thread,
  never from the GUI thread itself.
- The returned :class:`_AsyncMutationWaiter` resolves to the **actual**
  native result (same object the sync path returns), not a synthetic dict.
- Exceptions from the callback propagate as proven-rejection dicts or re-raised
  exceptions, identical to the non-GUI-thread sync path.

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


# A distinctive sentinel result that the fake sync method returns.
# Tests assert the *exact same object* is delivered by the waiter — not
# a synthetic {"status": "Committed", "committed": True} copy.
_SENTINEL_RESULT = {
    "status": "Committed",
    "committed": True,
    "operation_id": "test-op-42",
    "message": "sentinel commit",
    "conflicts": [],
    "published_revisions": [7],
}


class _FakeBodyDoc:
    """Document fake exposing the sync mutation surface.

    The background-thread path calls ``commitCompatibilityMutation`` from a
    worker thread.  The fake records which thread called it so tests can
    verify the GUI thread was never the caller.
    """

    def __init__(self, result: object = None) -> None:
        self.Name = "TestDoc"
        self.result = result if result is not None else dict(_SENTINEL_RESULT)
        self.sync_calls: list[tuple[Any, dict[str, Any]]] = []
        self.caller_threads: list[threading.Thread] = []

    # --- _NativeBodyDocument protocol ---

    def getObject(self, name: str) -> object:
        return None

    def addObject(self, object_type: str, name: str) -> object:
        return object()

    def commitCompatibilityMutation(self, callback, **kwargs):
        """Sync variant – called from the background thread, never the GUI thread."""
        self.sync_calls.append((callback, dict(kwargs)))
        self.caller_threads.append(threading.current_thread())
        callback()
        pc = kwargs.get("postcondition")
        if callable(pc):
            pc()
        return self.result


# ---------------------------------------------------------------------------
# Test: commit_body_create_mutation
# ---------------------------------------------------------------------------


def test_body_create_returns_actual_native_result_on_gui_thread(monkeypatch) -> None:
    """Waiter must deliver the real native result, not a synthetic dict."""
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    applied: list[object] = []

    def callback(d):
        applied.append(d)

    def postcondition(d):
        return True

    waiter = api.commit_body_create_mutation("TestDoc", callback, postcondition)

    # The waiter must be returned before the background thread completes.
    assert hasattr(waiter, "await_result"), "must return _AsyncMutationWaiter"

    # Await the actual result; the background thread runs the sync method.
    result = waiter.await_result(timeout=5.0)

    # The exact same object the fake sync method returns.
    assert result is doc.result, "waiter must return the actual native result object"
    assert result.get("operation_id") == "test-op-42", "operation_id must not be lost"
    assert result.get("published_revisions") == [7], "published_revisions must not be lost"

    # Sync method was called, but NOT from the main (GUI-spoofed) thread.
    assert doc.sync_calls, "sync method must have been called (by background thread)"
    gui_thread = threading.main_thread()
    for t in doc.caller_threads:
        assert t is not gui_thread, "sync method must not be called on the GUI thread"

    # Callback received the document.
    assert applied == [doc]


def test_body_create_sync_path_on_non_gui_thread(monkeypatch) -> None:
    """Sync path is used directly when NOT on the GUI thread."""
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: False)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    result = api.commit_body_create_mutation(
        "TestDoc", lambda d: None, lambda d: True
    )

    assert doc.sync_calls, "commitCompatibilityMutation must be called off GUI thread"
    assert result is doc.result, "sync path must return the native result"


def test_body_create_callback_raises_on_gui_thread(monkeypatch) -> None:
    """Callback exception → proven-rejection dict returned by waiter."""
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)

    class _ApplyError(Exception):
        pass

    def bad_callback(d):
        raise _ApplyError("apply failed")

    # Make the fake propagate the exception (simulating C++ rollback + re-raise).
    waiter = api.commit_body_create_mutation("TestDoc", bad_callback, lambda d: True)
    result = waiter.await_result(timeout=5.0)

    # The proven-rejection dict must be returned, not the exception re-raised.
    assert isinstance(result, dict), "proven rejection must be returned as dict"
    assert result.get("status") == "ApplyFailed"
    assert result.get("committed") is False
    assert result.get("rollback_succeeded") is True
    assert "apply failed" in result.get("message", "")


# ---------------------------------------------------------------------------
# Test: commit_native_mutation
# ---------------------------------------------------------------------------


def test_native_mutation_returns_actual_result_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    applied: list[object] = []

    def callback(d):
        applied.append(d)
        return True

    waiter = api.commit_native_mutation("TestDoc", callback, lambda d: True)
    result = waiter.await_result(timeout=5.0)

    assert result is doc.result, "waiter must return actual native result"
    assert applied == [doc]

    gui_thread = threading.main_thread()
    for t in doc.caller_threads:
        assert t is not gui_thread


def test_native_mutation_callback_raises_on_gui_thread(monkeypatch) -> None:
    """Callback exception → proven-rejection dict returned by waiter."""
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)

    class _NativeError(Exception):
        pass

    waiter = api.commit_native_mutation(
        "TestDoc",
        lambda d: (_ for _ in ()).throw(_NativeError("native failed")),  # type: ignore[misc]
        lambda d: True,
    )
    result = waiter.await_result(timeout=5.0)

    assert result.get("status") == "ApplyFailed"
    assert result.get("committed") is False
    assert result.get("rollback_succeeded") is True


# ---------------------------------------------------------------------------
# Test: commit_compatibility_mutation
# ---------------------------------------------------------------------------


def test_compat_mutation_returns_actual_result_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    called: list[bool] = []
    callback = lambda: called.append(True)  # noqa: E731

    waiter = api.commit_compatibility_mutation("TestDoc", callback)
    result = waiter.await_result(timeout=5.0)

    assert result is doc.result, "waiter must return actual native result"
    assert called == [True], "callback must have been called by background thread"


def test_compat_mutation_with_postcondition_on_gui_thread(monkeypatch) -> None:
    mod = _load_module()
    doc = _FakeBodyDoc()
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    callback_ran: list[bool] = []
    postcondition_ran: list[bool] = []

    waiter = api.commit_compatibility_mutation(
        "TestDoc",
        lambda: callback_ran.append(True),
        postcondition=lambda: postcondition_ran.append(True) or True,
    )
    result = waiter.await_result(timeout=5.0)

    assert result is doc.result
    assert callback_ran == [True]
    assert postcondition_ran == [True]


def test_compat_mutation_callback_raises_on_gui_thread(monkeypatch) -> None:
    """Callback exception raises from waiter (no proven_rejection for compat path)."""
    mod = _load_module()
    doc = _FakeBodyDoc()
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
# Test: await off the GUI thread via real background threads
# ---------------------------------------------------------------------------


def test_await_result_off_gui_thread(monkeypatch) -> None:
    """The awaiter must be safe to call from a non-GUI background thread."""
    mod = _load_module()
    doc = _FakeBodyDoc()
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


def test_sync_path_on_gui_thread_calls_background_not_caller(monkeypatch) -> None:
    """No matter which thread is 'GUI', the sync method is called on a worker."""
    mod = _load_module()
    doc = _FakeBodyDoc()

    caller_thread_id = threading.current_thread().ident
    monkeypatch.setattr(mod, "_is_freecad_gui_thread", lambda: True)

    api = mod.CollaborationAPI(document_lookup=lambda _name: doc)
    waiter = api.commit_body_create_mutation(
        "TestDoc", lambda d: None, lambda d: True
    )
    waiter.await_result(timeout=5.0)

    assert doc.caller_threads, "sync method must have been called"
    for t in doc.caller_threads:
        assert t.ident != caller_thread_id, (
            "sync method must not run on the calling (GUI) thread"
        )
