"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

import os
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
    callback: Callable[[], Any],
    *,
    has_postcondition: bool,
    require_native: bool,
) -> dict[str, object]:
    if has_postcondition:
        return _unsupported("native postcondition callback is not supported")
    if require_native:
        return _unsupported("document must provide commitCompatibilityMutation()")
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") == "1":
        raise TypeError("document must provide commitCompatibilityMutation()")
    callback()
    return {"status": "Committed", "committed": True}


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

        callback_started: list[bool] = []

        def invoke_callback() -> object:
            callback_started.append(True)
            return callback(document)

        def invoke_postcondition() -> object:
            return postcondition(document)

        try:
            return document.commitCompatibilityMutation(
                invoke_callback,
                structural=True,
                postcondition=invoke_postcondition,
            )
        except TypeError:
            if not callback_started:
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

        callback_started: list[bool] = []

        def invoke_callback() -> object:
            callback_started.append(True)
            return callback(document)

        def invoke_postcondition() -> object:
            return postcondition(document)

        try:
            return document.commitCompatibilityMutation(
                invoke_callback,
                structural=structural,
                postcondition=invoke_postcondition,
            )
        except TypeError:
            if not callback_started:
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
                invoke_callback,
                has_postcondition=postcondition is not None,
                require_native=require_native,
            )
        options: dict[str, Any] = {"structural": structural}
        if postcondition is not None:
            options["postcondition"] = invoke_postcondition
        native_callback = (
            invoke_callback
            if bind_document or (require_native and postcondition is not None)
            else callback
        )
        try:
            return commit(native_callback, **options)
        except TypeError:
            # An older native binding rejects the new keyword before invoking
            # the callback. Report a closed, non-mutating rejection for the
            # explicitly native-only path.
            if require_native and postcondition is not None and not callback_started:
                return _unsupported("native postcondition callback is not supported")
            raise
