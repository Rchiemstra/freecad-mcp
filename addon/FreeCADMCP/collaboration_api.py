"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

try:
    from .document_recompute_settlement import settle_document_must_execute
except ImportError:  # pragma: no cover - flat addon import path
    from document_recompute_settlement import (  # type: ignore[import-not-found]
        settle_document_must_execute,
    )

if TYPE_CHECKING:
    from ._shared.protocol.body_create_contract import (
        BodyDocument,
        BodyObject,
        BodyReadDocument,
        DocumentName,
    )


@runtime_checkable
class _NativeBodyDocument(Protocol):
    """Runtime surface checked before the Body callback can be invoked."""

    Name: str

    def getObject(self, name: str) -> BodyObject | None: ...

    def addObject(self, object_type: str, name: str) -> BodyObject: ...

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
    ) -> object: ...


@runtime_checkable
class _NativeMutationDocument(Protocol):
    """Runtime surface checked before a typed native callback can be invoked."""

    Name: str

    def commitCompatibilityMutation(
        self,
        callback: Callable[[], object],
        *,
        structural: bool = False,
        postcondition: Callable[[], object] | None = None,
        recompute: bool = True,
    ) -> object: ...

__all__ = ["CollaborationAPI"]


# ---------------------------------------------------------------------------
# GUI-thread detection and async mutation waiter
# ---------------------------------------------------------------------------

def _freecad_gui_up() -> bool:
    """Return whether FreeCAD's GUI is initialised in this process.

    The C++ ``DocumentWouldBlock`` rule only applies once the GUI has
    installed its main-thread hooks, which happens with ``FreeCAD.GuiUp``.  A
    bare ``QCoreApplication`` (FreeCADCmd, tests) never refuses sync calls.
    """
    try:
        import FreeCAD
    except ImportError:
        return False
    return getattr(FreeCAD, "GuiUp", 0) in (1, True)


def _is_freecad_gui_thread() -> bool:
    """Return ``True`` when called on the FreeCAD/Qt GUI main thread.

    Uses Qt's thread-affinity query so it works regardless of how FreeCAD
    started Python.  Returns ``False`` in headless runs, where the GUI is not
    up or there is no ``QCoreApplication`` instance.
    """
    if not _freecad_gui_up():
        return False
    # FreeCAD's ``PySide`` shim maps to the Qt binding the GUI runs on.  Never
    # probe PySide2 directly: a stray system PySide2 next to a Qt6 FreeCAD
    # fails inside its ``__init__`` with NameError, not ImportError.
    try:
        from PySide.QtCore import QCoreApplication, QThread  # type: ignore[import-not-found]
    except ImportError:
        return False
    app = QCoreApplication.instance()
    if app is None:
        return False
    return QThread.currentThread() is app.thread()


class _AsyncMutationWaiter:
    """Returned from a GUI-thread commit call so the RPC thread can wait.

    The GUI callable calls ``commitCompatibilityMutationAsync`` (the
    non-blocking C++ binding that posts work to the document's owner thread)
    and wraps the returned ``wait()`` callable in this object.  The RPC
    thread — already unblocked from ``dispatch_to_gui`` — calls
    :meth:`await_result` to block on the C++ future without holding the
    GUI event loop.

    *refusals* is the :class:`_CallbackRefusals` from the same call frame
    so that proven-rollback rejections can be returned as dicts (matching
    the sync path) rather than re-raised exceptions.
    """

    __slots__ = ("_wait_fn", "_refusals")

    def __init__(
        self,
        wait_fn: Callable[[float], object],
        refusals: _CallbackRefusals | None = None,
    ) -> None:
        self._wait_fn = wait_fn
        self._refusals = refusals

    def await_result(self, timeout: float = 60.0) -> object:
        """Block the calling thread until the async mutation completes.

        Calls the C++ ``wait(timeout)`` callable which releases the GIL,
        blocks on ``std::future::wait_for``, then returns the commit result
        dict — the same object the sync path returns — or raises the
        original callback/postcondition exception.

        Proven-rollback rejections (callback raised after a completed
        rollback) are caught and returned as dicts, matching the sync path's
        ``proven_rejection`` path.  All other exceptions propagate unchanged.
        """
        try:
            return self._wait_fn(timeout)
        except Exception as exc:
            if self._refusals is not None:
                rejection = self._refusals.proven_rejection(exc)
                if rejection is not None:
                    return rejection
            raise


def _commit_async_on_gui_thread(
    document: object,
    callback: Callable[[], object],
    async_kwargs: Mapping[str, object],
    refusals: _CallbackRefusals | None,
) -> _AsyncMutationWaiter:
    """Call ``commitCompatibilityMutationAsync`` and return a waiter immediately.

    The GUI thread must never call ``document.commitCompatibilityMutation``
    (sync) because the C++ binding raises ``DocumentWouldBlock`` from the Qt
    main thread.  The async variant posts the same work to the document's
    owner thread via ``DocumentExecutionLane::postToOwner``, avoiding any
    blocking on the GUI thread.

    The returned :class:`_AsyncMutationWaiter` wraps the C++ ``wait()``
    callable embedded in the handle dict.  The RPC thread (blocked in
    ``dispatch_to_gui`` and unblocked when the GUI callable returns) calls
    ``waiter.await_result(timeout)`` which blocks inside C++ without holding
    the Qt event loop.

    The C++ ``wait()`` callable releases the GIL, calls
    ``std::future::wait_for``, and on completion either returns the
    ``commitResultToPython`` dict (the exact same object the sync path
    returns, including ``operation_id``, ``message``, ``conflicts``, and
    ``published_revisions``) or restores and re-raises the
    callback/postcondition exception on the waiting thread.

    Raises ``RuntimeError`` when either the async binding is absent
    (headless or older FreeCAD) or the returned handle does not carry a
    ``wait()`` callable (FreeCAD version mismatch).
    """
    commit_async = getattr(document, "commitCompatibilityMutationAsync", None)
    if not callable(commit_async):
        raise RuntimeError(
            "commitCompatibilityMutationAsync is not available on this document "
            "object; the GUI thread must not call the synchronous "
            "commitCompatibilityMutation"
        )
    handle = commit_async(callback, **async_kwargs)
    wait_fn = handle.get("wait") if isinstance(handle, dict) else None
    if not callable(wait_fn):
        raise RuntimeError(
            "commitCompatibilityMutationAsync did not return a handle with a "
            "wait() callable; FreeCAD may need to be updated"
        )
    return _AsyncMutationWaiter(wait_fn, refusals)


# ---------------------------------------------------------------------------
# Internal helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _unsupported(message: str) -> dict[str, object]:
    return {"status": "Unsupported", "committed": False, "message": message}


def _validate_callbacks(
    callback: Callable[..., Any], postcondition: Callable[..., Any] | None
) -> None:
    if not callable(callback):
        raise TypeError("callback must be callable")
    if postcondition is not None and not callable(postcondition):
        raise TypeError("postcondition must be callable or None")


def _settle_pending_recompute(document: object) -> None:
    """Clear leftover mustExecute so the next native commit is not Busy."""

    settle_document_must_execute(document)


def _commit_without_native(
    *,
    has_postcondition: bool,
    require_native: bool,
) -> dict[str, object]:
    if has_postcondition:
        return _unsupported("native postcondition callback is not supported")
    if require_native:
        return _unsupported("document must provide commitCompatibilityMutation()")
    # Main fail-closed: never run the callback on a document that cannot
    # attribute the mutation. Typed-rpc still returns Unsupported when the
    # caller explicitly required a native postcondition or native-only lane.
    raise TypeError("document must provide commitCompatibilityMutation()")


class _CallbackRefusals:
    """Remember the exceptions our own native callbacks raised.

    ``DocumentPy::commitCompatibilityMutation`` re-raises a failed apply or
    postcondition callback's exception only after the coordinator restored the
    document; a failed rollback is returned as a ``RollbackFailed`` result
    instead. The very exception object raised by our callback escaping the
    binding therefore proves a completed rollback. Any other exception stays
    unproven and keeps propagating.
    """

    __slots__ = ("_raised", "started")

    def __init__(self) -> None:
        self.started = False
        self._raised: list[tuple[str, BaseException]] = []

    def record(self, status: str, exc: BaseException) -> None:
        self._raised.append((status, exc))

    def proven_rejection(self, exc: BaseException) -> dict[str, object] | None:
        for status, raised in self._raised:
            if raised is exc:
                return {
                    "status": status,
                    "committed": False,
                    "rollback_succeeded": True,
                    "message": str(exc) or type(exc).__name__,
                }
        return None


class CollaborationAPI:
    """Resolve a document and invoke its native compatibility commit binding."""

    __slots__ = ("_document_lookup",)

    def __init__(self, *, document_lookup: Callable[[str], object]) -> None:
        if not callable(document_lookup):
            raise TypeError("document_lookup must be callable")
        self._document_lookup = document_lookup

    def _resolve_admitted_document(self, document_name: str) -> object:
        try:
            document = self._document_lookup(document_name)
        except NameError as exc:
            # FreeCAD.getDocument raises NameError for a missing document.
            raise LookupError(str(exc)) from exc
        if document is None:
            raise LookupError("document_lookup returned no document")
        return document

    def commit_body_create_mutation(
        self,
        document_name: DocumentName,
        callback: Callable[[BodyDocument], object],
        postcondition: Callable[[BodyReadDocument], object],
    ) -> object:
        """Run Body creation only when the exact native contract is present."""

        document = self._resolve_admitted_document(document_name)
        if not isinstance(document, _NativeBodyDocument):
            return _unsupported(
                "document must provide the native Body mutation contract"
            )

        _settle_pending_recompute(document)
        refusals = _CallbackRefusals()

        def invoke_callback() -> object:
            refusals.started = True
            try:
                return callback(document)
            except Exception as exc:
                refusals.record("ApplyFailed", exc)
                raise

        def invoke_postcondition() -> object:
            try:
                return postcondition(document)
            except Exception as exc:
                refusals.record("PostconditionFailed", exc)
                raise

        if _is_freecad_gui_thread():
            # B4: Never call the blocking sync variant on the GUI thread.
            # Use commitCompatibilityMutationAsync so the owner-thread work is
            # posted without blocking the event loop.  The RPC thread waits.
            return _commit_async_on_gui_thread(
                document,
                invoke_callback,
                {"structural": True, "postcondition": invoke_postcondition},
                refusals,
            )

        try:
            return document.commitCompatibilityMutation(
                invoke_callback,
                structural=True,
                postcondition=invoke_postcondition,
            )
        except Exception as exc:
            rejection = refusals.proven_rejection(exc)
            if rejection is not None:
                return rejection
            if isinstance(exc, TypeError) and not refusals.started:
                return _unsupported(
                    "native postcondition callback is not supported"
                )
            raise

    def commit_native_mutation(
        self,
        document_name: str,
        callback: Callable[[object], object],
        postcondition: Callable[[object], object],
        *,
        structural: bool = True,
        recompute: bool = True,
    ) -> object:
        """Run a typed native mutation with apply and inspect on one document."""

        document = self._resolve_admitted_document(document_name)
        if not isinstance(document, _NativeMutationDocument):
            return _unsupported(
                "document must provide the native typed mutation contract"
            )

        if recompute:
            _settle_pending_recompute(document)
        refusals = _CallbackRefusals()

        def invoke_callback() -> object:
            refusals.started = True
            try:
                return callback(document)
            except Exception as exc:
                refusals.record("ApplyFailed", exc)
                raise

        def invoke_postcondition() -> object:
            try:
                return postcondition(document)
            except Exception as exc:
                refusals.record("PostconditionFailed", exc)
                raise

        if _is_freecad_gui_thread():
            # B4: Never call the blocking sync variant on the GUI thread.
            return _commit_async_on_gui_thread(
                document,
                invoke_callback,
                {
                    "structural": structural,
                    "postcondition": invoke_postcondition,
                    "recompute": recompute,
                },
                refusals,
            )

        try:
            return document.commitCompatibilityMutation(
                invoke_callback,
                structural=structural,
                postcondition=invoke_postcondition,
                recompute=recompute,
            )
        except Exception as exc:
            rejection = refusals.proven_rejection(exc)
            if rejection is not None:
                return rejection
            if isinstance(exc, TypeError) and not refusals.started:
                return _unsupported(
                    "native postcondition callback is not supported"
                )
            raise

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[..., Any],
        *,
        structural: bool = False,
        recompute: bool = True,
        postcondition: Callable[..., Any] | None = None,
        bind_document: bool = False,
        require_native: bool = False,
    ) -> Any:
        """Return the native result after invoking ``callback`` at the commit boundary."""

        _validate_callbacks(callback, postcondition)

        document = self._document_lookup(document_name)
        if document is None:
            raise LookupError("document_lookup returned no document")

        callback_started: list[bool] = []

        def invoke_callback() -> Any:
            callback_started.append(True)
            return callback(document) if bind_document else callback()

        def invoke_postcondition() -> Any:
            if postcondition is None:
                return True
            return postcondition(document) if bind_document else postcondition()

        commit = getattr(document, "commitCompatibilityMutation", None)
        if not callable(commit):
            return _commit_without_native(
                has_postcondition=postcondition is not None,
                require_native=require_native,
            )

        options: dict[str, Any] = {"structural": structural}
        if not recompute:
            # Deferred recompute is an ordering contract: only pass the keyword
            # when the caller explicitly opts out of the native coordinator.
            options["recompute"] = False
        if postcondition is not None:
            # A postcondition is an ordering contract, not an optional
            # convenience. Passing the keyword deliberately fails before the
            # callback on an older native runtime instead of silently moving
            # validation back in front of the native recompute.
            # KEEP BOTH: main forwards the original postcondition identity
            # unless bind_document requires a wrapper that injects the admitted
            # document.
            options["postcondition"] = (
                invoke_postcondition if bind_document else postcondition
            )
        native_callback = invoke_callback if bind_document else callback
        if require_native and postcondition is not None:
            # Track whether the native binding invoked the callback before
            # rejecting an unknown postcondition keyword.
            native_callback = invoke_callback

        if _is_freecad_gui_thread():
            # B4: Never call the blocking sync variant on the GUI thread.
            # options and native_callback are already computed identically to
            # the sync path; reuse them for the async call.
            try:
                return _commit_async_on_gui_thread(
                    document, native_callback, options, None
                )
            except TypeError:
                if require_native and postcondition is not None and not callback_started:
                    return _unsupported("native postcondition callback is not supported")
                raise

        try:
            return commit(native_callback, **options)
        except TypeError:
            # An older native binding rejects the new keyword before invoking
            # the callback. Report a closed, non-mutating rejection for the
            # explicitly native-only path.
            if require_native and postcondition is not None and not callback_started:
                return _unsupported("native postcondition callback is not supported")
            raise
