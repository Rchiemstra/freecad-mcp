"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = ["CollaborationAPI"]


class CollaborationAPI:
    """Resolve a document and invoke its native compatibility commit binding."""

    __slots__ = ("_document_lookup",)

    def __init__(self, *, document_lookup: Callable[[str], object]) -> None:
        if not callable(document_lookup):
            raise TypeError("document_lookup must be callable")
        self._document_lookup = document_lookup

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
        *,
        structural: bool = False,
        recompute: bool = True,
        postcondition: Callable[[], Any] | None = None,
    ) -> Any:
        """Return the native result after invoking ``callback`` at the commit boundary."""

        if not callable(callback):
            raise TypeError("callback must be callable")
        if postcondition is not None and not callable(postcondition):
            raise TypeError("postcondition must be callable")

        document = self._document_lookup(document_name)
        if document is None:
            raise LookupError("document_lookup returned no document")

        commit = getattr(document, "commitCompatibilityMutation", None)
        if not callable(commit):
            raise TypeError("document must provide commitCompatibilityMutation()")
        native_options: dict[str, Any] = {"structural": structural}
        if structural:
            # The public MCP surface never accepts native authority.  Only an
            # internal typed/generated operation that selected structural
            # scope can request the matching native trust grant.  An older
            # runtime rejects this keyword before invoking the callback.
            native_options["trusted_structural"] = True
        if not recompute:
            native_options["recompute"] = False
        if postcondition is not None:
            # A postcondition is an ordering contract, not an optional
            # convenience.  Passing the keyword deliberately fails before the
            # callback on an older native runtime instead of silently moving
            # validation back in front of the native recompute.
            native_options["postcondition"] = postcondition
        return commit(callback, **native_options)
