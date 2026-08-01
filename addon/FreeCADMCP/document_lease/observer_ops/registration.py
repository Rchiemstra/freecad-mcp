"""Idempotent App and GUI observer registration."""

from __future__ import annotations

import contextlib
import importlib
from typing import Any

from .. import observer as observer_mod
from ._log import logger
from .app_observer import LeaseObserver
from .events import (
    AgentMutationChecker,
    DocumentProvider,
    NotificationCallback,
    NotificationQueue,
    ServiceProvider,
)
from .gui_observer import LeaseGuiObserver


def register_observer(
    *,
    freecad_module: Any | None = None,
    freecad_gui_module: Any | None = None,
    service_provider: ServiceProvider | None = None,
    agent_mutation_checker: AgentMutationChecker | None = None,
    selected_document_provider: DocumentProvider | None = None,
    notification_callback: NotificationCallback | None = None,
    notification_queue: NotificationQueue | None = None,
) -> LeaseObserver | None:
    """Register the App and optional GUI observers idempotently."""

    with observer_mod._registration_lock:
        if observer_mod._app_observer is not None:
            return observer_mod._app_observer
        if freecad_module is None:
            try:
                freecad_module = importlib.import_module("FreeCAD")
            except Exception:
                return None
        add_observer = getattr(freecad_module, "addDocumentObserver", None)
        if not callable(add_observer):
            return None
        observer = LeaseObserver(
            service_provider=service_provider,
            agent_mutation_checker=agent_mutation_checker,
            selected_document_provider=selected_document_provider,
            notification_callback=notification_callback,
            notification_queue=notification_queue,
        )
        add_observer(observer)
        observer_mod._app_observer = observer
        observer_mod._registered_freecad = freecad_module
        with contextlib.suppress(Exception):
            freecad_module._mcp_document_lease_observer = observer

        if freecad_gui_module is None:
            try:
                freecad_gui_module = importlib.import_module("FreeCADGui")
            except Exception:
                freecad_gui_module = None
        add_gui_observer = (
            getattr(freecad_gui_module, "addDocumentObserver", None)
            if freecad_gui_module is not None
            else None
        )
        if callable(add_gui_observer):
            gui_observer = LeaseGuiObserver(observer)
            try:
                add_gui_observer(gui_observer)
                observer_mod._gui_observer = gui_observer
                observer_mod._registered_freecad_gui = freecad_gui_module
                with contextlib.suppress(Exception):
                    freecad_gui_module._mcp_document_lease_gui_observer = gui_observer
            except Exception:
                logger.warning("unable to register GUI lease observer", exc_info=True)
        return observer


def unregister_observer() -> None:
    """Unregister both observers without changing any lease or sidecar."""

    with observer_mod._registration_lock:
        app_observer = observer_mod._app_observer
        gui_observer = observer_mod._gui_observer
        freecad_module = observer_mod._registered_freecad
        freecad_gui_module = observer_mod._registered_freecad_gui
        observer_mod._app_observer = None
        observer_mod._gui_observer = None
        observer_mod._registered_freecad = None
        observer_mod._registered_freecad_gui = None

        remove_gui = (
            getattr(freecad_gui_module, "removeDocumentObserver", None)
            if freecad_gui_module is not None
            else None
        )
        if gui_observer is not None and callable(remove_gui):
            try:
                remove_gui(gui_observer)
            except Exception:
                logger.debug("unable to unregister GUI lease observer", exc_info=True)
        remove_app = (
            getattr(freecad_module, "removeDocumentObserver", None)
            if freecad_module is not None
            else None
        )
        if app_observer is not None and callable(remove_app):
            try:
                remove_app(app_observer)
            except Exception:
                logger.debug("unable to unregister App lease observer", exc_info=True)

        for module, attr, expected in (
            (freecad_module, "_mcp_document_lease_observer", app_observer),
            (
                freecad_gui_module,
                "_mcp_document_lease_gui_observer",
                gui_observer,
            ),
        ):
            try:
                if module is not None and getattr(module, attr, None) is expected:
                    delattr(module, attr)
            except Exception:
                pass


def take_over_selected_document(
    *,
    service_provider: ServiceProvider | None = None,
    selected_document_provider: DocumentProvider | None = None,
    notification_callback: NotificationCallback | None = None,
    notification_queue: NotificationQueue | None = None,
    reason: str = "Local user selected Take Over",
) -> Any | None:
    """Fence the active document for a confirmed local GUI takeover action."""

    observer = LeaseObserver(
        service_provider=service_provider,
        selected_document_provider=selected_document_provider,
        notification_callback=notification_callback,
        notification_queue=notification_queue,
    )
    return observer.take_over_selected_document(reason=reason)
