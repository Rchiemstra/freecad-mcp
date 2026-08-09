"""Explicit process and restart-scoped collaborators for the lock indicator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LockIndicatorRuntimeBindings:
    """Typed collaborators installed by the add-on composition root.

    Providers are used only for identities that can change across RPC runtime
    restarts.  Operation callbacks are captured directly and never discovered
    through Python's module registry.
    """

    freecad: Any
    current_lease_service: Callable[[], Any | None]
    current_gui_dispatcher: Callable[[], Any | None]
    current_save_service: Callable[[], Any | None]
    list_compatibility_leases: Callable[[], Any]
    inspect_compatibility_lease: Callable[[str], Any | None]
    compatibility_process_alive: Callable[[int], bool]
    mark_compatibility_lease_user_intervened: Callable[[str], Any | None]
    set_compatibility_gui_update_callback: Callable[[Callable[[], None]], None]
    recovery_snapshot_path: Callable[[str], Any]
    restore_snapshot_in_place_gui: Callable[..., Mapping[str, Any]]
    validate_document_invariants: Callable[[Any], Mapping[str, Any]]
    saved_document_expectations: Callable[[Any], Mapping[str, Any]]
    validate_saved_document_worker: Callable[..., Mapping[str, Any]]
    discard_terminal_snapshot: Callable[[Any], Any]


_runtime_bindings: LockIndicatorRuntimeBindings | None = None


def bind_runtime_bindings(bindings: LockIndicatorRuntimeBindings) -> None:
    """Install the exact collaborators assembled by the RPC composition root."""

    if not isinstance(bindings, LockIndicatorRuntimeBindings):
        raise TypeError("bindings must be LockIndicatorRuntimeBindings")
    global _runtime_bindings
    _runtime_bindings = bindings


def current_runtime_bindings() -> LockIndicatorRuntimeBindings | None:
    """Return the explicitly installed collaborator set, when initialized."""

    return _runtime_bindings
