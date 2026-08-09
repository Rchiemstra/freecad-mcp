"""Drain queued GUI-thread callables and optionally reschedule."""

from __future__ import annotations

import time

from PySide import QtCore

from . import queue_state
from .defer_checks import should_defer_gui_processing
from .task_drain import clear_processing_ui_context, drain_task_queue, processing_ui_context


def process_gui_tasks(reschedule: bool = True) -> None:
    """Drain queued GUI-thread callables and optionally reschedule.

    Skips the current tick when any mouse button is held (e.g., 3D navigation
    drag) or when already executing a task (re-entrancy guard). The guard
    prevents ``doc.recompute()`` or ``processEvents()`` inside a task from
    triggering a nested ``process_gui_tasks`` call that corrupts FreeCAD state.

    ``reschedule=False`` is used by the immediate-wake path so it does not
    start a second heartbeat chain alongside the existing 500 ms one.
    """
    if queue_state.processing:
        return

    shutdown = False
    try:
        if should_defer_gui_processing():
            return

        queue_state.processing = True
        queue_state.processing_since = time.monotonic()
        app, status_bar = processing_ui_context()
        try:
            shutdown = drain_task_queue()
        finally:
            clear_processing_ui_context(app, status_bar)
    finally:
        queue_state.processing = False
        if not shutdown and reschedule:
            QtCore.QTimer.singleShot(500, process_gui_tasks)
