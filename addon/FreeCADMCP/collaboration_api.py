"""Thin add-on bridge to FreeCAD's native collaboration boundary."""

from __future__ import annotations

import os
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
    ) -> Any:
        """Return the native result after invoking ``callback`` at the commit boundary."""

        if not callable(callback):
            raise TypeError("callback must be callable")

        document = self._document_lookup(document_name)
        if document is None:
            raise LookupError("document_lookup returned no document")

        commit = getattr(document, "commitCompatibilityMutation", None)
        if not callable(commit):
            if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") == "1":
                raise TypeError("document must provide commitCompatibilityMutation()")
            callback()
            return {"status": "Committed", "committed": True}
        return commit(callback, structural=structural)
