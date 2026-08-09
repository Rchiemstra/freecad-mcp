"""Clickable status-bar label for the lock indicator."""

from __future__ import annotations

from typing import Any


def clickable_status_label_type(qt_widgets: Any, qt_core: Any) -> type:
    class _ClickableStatusLabel(qt_widgets.QLabel):
        clicked = qt_core.Signal()

        def mouseReleaseEvent(self, event):  # type: ignore[no-untyped-def]
            super().mouseReleaseEvent(event)
            self.clicked.emit()

    return _ClickableStatusLabel
