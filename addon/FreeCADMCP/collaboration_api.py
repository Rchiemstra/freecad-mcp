"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

import threading
from collections.abc import Callable
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

def _is_freecad_gui_thread() -> bool:
    """Return ``True`` when called on the FreeCAD/Qt GUI main thread.

    Uses Qt's thread-affinity query so it works regardless of how FreeCAD
    started Python.  Returns ``False`` in headless runs where there is no
    ``QCoreApplication`` instance.
    """
    try:
        from PySide2.QtCore import QCoreApplication, QThread  # type: ignore[import]
    except ImportError:
        try:
            from PySide.QtCore import QCoreApplication, QThread  # type: ignore[import]
        except ImportError:
            return False
    app = QCoreApplication.instance()
    if app is None:
        return False
    return QThread.currentThread() is app.thread()


class _AsyncMutationWaiter:
    """Returned from a GUI-thread commit call so the RPC thread can wait.

    The GUI callable sets up a :class:`threading.Event` and returns this
    object immediately.  The RPC thread (unblocked from ``dispatch_to_gui``)
    calls :meth:`await_result` to block until the owner thread has finished
    the mutation and the event has been set.

    ``refusals`` is the :class:`_CallbackRefusals` from the same call frame
    so that proven-rollback rejections can be returned as dicts (matching the
    sync path) instead of re-raised exceptions.
    """

    __slots__ = ("_event", "_refusals", "_result_holder")

    def __init__(
        self,
        event: threading.Event,
        result_holder: list,
        refusals: _CallbackRefusals | None = None,
    ) -> None:
        self._event = event
        self._result_holder = result_holder
        self._refusals = refusals

    def await_result(self, timeout: float = 60.0) -> Any:
        """Block the calling thread until the async mutation completes.

        Returns the commit result dict on success.  On failure raises the
        original exception, unless the exception was a proven callback
        rejection (completed rollback), in which case it returns the
        rejection dict—matching the sync path's ``proven_rejection`` path.
        """
        if not self._event.wait(timeout):
            raise TimeoutError(
                "async GUI-thread mutation did not complete within "
                f"{timeout}s timeout"
            )
        if not self._result_holder:
            raise RuntimeError(
                "async GUI-thread mutation completed without a result record"
            )
        status, value = self._result_holder[0]
        if status == "error":
            if self._refusals is not None:
                rejection = self._refusals.proven_rejection(value)
                if rejection is not None:
                    return rejection
            raise value
        return value


def _commit_async_on_gui_thread(
    document: object,
    invoke_callback: Callable[[], object],
    invoke_postcondition: Callable[[], object] | None,
    refusals: _CallbackRefusals | None,
    *,
    structural: bool = False,
    recompute: bool = True,
    object_name: str | None = None,
) -> _AsyncMutationWaiter:
    """Submit a compatibility mutation from the GUI thread without blocking.

    Calls ``document.commitCompatibilityMutationAsync`` (the non-blocking
    variant) and returns an :class:`_AsyncMutationWaiter` immediately.  The
    async C++ binding posts the work to the document's owner thread; the RPC
    thread (blocked in ``dispatch_to_gui``) is the one that eventually calls
    ``waiter.await_result()`` to retrieve the final status.

    A synthetic signaling postcondition wraps *invoke_postcondition* (or
    supplies ``True`` when no user postcondition exists) so that the owner
    thread sets the threading event after the mutation is complete.  Callback
    and postcondition failures set the event with the original exception so
    ``await_result`` can re-raise or return a proven-rejection dict.

    Raises ``RuntimeError`` when ``commitCompatibilityMutationAsync`` is not
    present on the document (headless or older FreeCAD without the binding).
    On the GUI thread the caller must never fall back to the sync method.
    """
    commit_async = getattr(document, "commitCompatibilityMutationAsync", None)
    if not callable(commit_async):
        raise RuntimeError(
            "commitCompatibilityMutationAsync is not available on this document "
            "object; the GUI thread must not call the synchronous "
            "commitCompatibilityMutation"
        )

    event: threading.Event = threading.Event()
    result_holder: list = []

    def _signaling_callback() -> object:
        try:
            return invoke_callback()
        except Exception as exc:
            if not result_holder:
                result_holder.append(("error", exc))
                event.set()
            raise

    def _signaling_postcondition() -> object:
        if invoke_postcondition is not None:
            try:
                success = invoke_postcondition()
            except Exception as exc:
                if not result_holder:
                    result_holder.append(("error", exc))
                    event.set()
                raise
        else:
            success = True
        if not result_holder:
            if success:
                result_holder.append(("ok", {"status": "Committed", "committed": True}))
            else:
                result_holder.append(
                    ("ok", {"status": "PostconditionFailed", "committed": False})
                )
            event.set()
        return bool(success)

    kwargs: dict[str, Any] = {"structural": structural, "postcondition": _signaling_postcondition}
    if not recompute:
        kwargs["recompute"] = False
    if object_name is not None:
        kwargs["object_name"] = object_name

    commit_async(_signaling_callback, **kwargs)
    return _AsyncMutationWaiter(event, result_holder, refusals)


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

        # B4: On the GUI thread, never call the blocking sync variant.  Post
        # to the document's owner thread via the async binding and return a
        # waiter immediately; the RPC thread calls waiter.await_result().
        if _is_freecad_gui_thread():
            return _commit_async_on_gui_thread(
                document,
                invoke_callback,
                invoke_postcondition,
                refusals,
                structural=True,
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

        # B4: On the GUI thread use the non-blocking async binding.
        if _is_freecad_gui_thread():
            return _commit_async_on_gui_thread(
                document,
                invoke_callback,
                invoke_postcondition,
                refusals,
                structural=structural,
                recompute=recompute,
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

        # B4: On the GUI thread use the non-blocking async binding so the
        # event-loop thread is never stalled waiting for the owner thread.
        # The RPC thread (blocked in dispatch_to_gui) is the waiter.
        if _is_freecad_gui_thread():
            # invoke_postcondition already returns True when postcondition is
            # None, so passing it as the signaling postcondition is safe.
            return _commit_async_on_gui_thread(
                document,
                invoke_callback,
                invoke_postcondition if (postcondition is not None or bind_document) else None,
                None,  # _CallbackRefusals not tracked for this path
                structural=structural,
                recompute=recompute,
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
        try:
            return commit(native_callback, **options)
        except TypeError:
            # An older native binding rejects the new keyword before invoking
            # the callback. Report a closed, non-mutating rejection for the
            # explicitly native-only path.
            if require_native and postcondition is not None and not callback_started:
                return _unsupported("native postcondition callback is not supported")
            raise
