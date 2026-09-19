"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

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
    ) -> object: ...

__all__ = ["CollaborationAPI"]


def _unsupported(message: str) -> dict[str, object]:
    return {"status": "Unsupported", "committed": False, "message": message}


def _validate_callbacks(
    callback: Callable[..., Any], postcondition: Callable[..., Any] | None
) -> None:
    if not callable(callback):
        raise TypeError("callback must be callable")
    if postcondition is not None and not callable(postcondition):
        raise TypeError("postcondition must be callable or None")


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
    ) -> object:
        """Run a typed native mutation with apply and inspect on one document."""

        document = self._resolve_admitted_document(document_name)
        if not isinstance(document, _NativeMutationDocument):
            return _unsupported(
                "document must provide the native typed mutation contract"
            )

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

        try:
            return document.commitCompatibilityMutation(
                invoke_callback,
                structural=structural,
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
        try:
            return commit(native_callback, **options)
        except TypeError:
            # An older native binding rejects the new keyword before invoking
            # the callback. Report a closed, non-mutating rejection for the
            # explicitly native-only path.
            if require_native and postcondition is not None and not callback_started:
                return _unsupported("native postcondition callback is not supported")
            raise
