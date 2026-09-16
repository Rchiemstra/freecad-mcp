"""Synchronous GUI dispatch fake matching production ``dispatch_gui`` submit.

Production ``dispatch_gui`` returns ``dispatcher.submit(gui_task, timeout, ...)``
immediately. ``late_result_transform`` is applied later by
``build_replay_on_complete``, not on the synchronous return path.

Core tests that used ``lambda callback: callback()`` rejected
``late_result_transform=`` (Woodpecker 348/22). This helper accepts the
production kwargs and runs the task on the calling thread.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def synchronous_dispatch_gui(
    task: Callable[[], Any],
    timeout=None,
    *,
    late_on_complete=None,
    late_result_transform=None,
    journal_late_completion=True,
    **_kwargs,
):
    del timeout, late_on_complete, late_result_transform, journal_late_completion
    return task()
