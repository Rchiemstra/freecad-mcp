"""Authoritative native-readiness fixtures for mutation unit tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def ready_native_readiness() -> dict[str, Any]:
    return {
        "ready": True,
        "stable_event_supported": True,
        "pending_transaction": False,
        "booked_transaction": 0,
        "transaction_locked": False,
        "recomputing": False,
        "must_execute": False,
        "pending_removal": False,
        "commit_barrier": False,
        "notification_replay": False,
        "poisoned": False,
        "quarantined": False,
        "diagnostic": "Ready for mutation",
    }


def attach_native_readiness(document: Any) -> Any:
    """Give a mutable test double the now-required native readiness API."""

    if document is not None and not callable(
        getattr(document, "getMutationReadiness", None)
    ):
        document.getMutationReadiness = ready_native_readiness
    return document


class _ReadinessFreeCADProxy:
    def __init__(self, target: Any) -> None:
        self._target = target

    def getDocument(self, name: str) -> Any:
        return attach_native_readiness(self._target.getDocument(name))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


def freecad_with_native_readiness(freecad: Any | None = None) -> Any:
    """Wrap a test FreeCAD facade while preserving returned document identity."""

    if freecad is None:
        document = attach_native_readiness(SimpleNamespace(Name="Doc"))
        freecad = SimpleNamespace(
            getDocument=lambda name: document if name == document.Name else None
        )
    lookup = getattr(freecad, "getDocument", None)
    if not callable(lookup):
        raise TypeError("test FreeCAD facade must provide getDocument()")
    return _ReadinessFreeCADProxy(freecad)


__all__ = [
    "attach_native_readiness",
    "freecad_with_native_readiness",
    "ready_native_readiness",
]
