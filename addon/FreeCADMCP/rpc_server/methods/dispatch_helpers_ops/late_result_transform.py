"""Apply ``late_result_transform`` on the replay/journal path only.

Production ``dispatch_gui`` returns ``dispatcher.submit(...)`` immediately.
The transform is for ``build_replay_on_complete``, not the synchronous return.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def apply_late_result_transform(
    result: Any,
    result_transform: Callable[[Any], Any] | None,
) -> tuple[Any, Exception | None]:
    """Return ``(result, error)``. ``error`` is set when the transform raises."""
    if result_transform is None:
        return result, None
    try:
        return result_transform(result), None
    except Exception as exc:
        return result, exc
