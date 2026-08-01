"""Observer notification event and callback type aliases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ServiceProvider = Callable[[], Any | None]
AgentMutationChecker = Callable[[str], bool]
DocumentProvider = Callable[[], Any | None]
NotificationCallback = Callable[["LeaseObserverEvent"], None]
NotificationQueue = Callable[[Callable[[], None]], None]


@dataclass(frozen=True)
class LeaseObserverEvent:
    """Token-free notification emitted after an owner has been fenced."""

    kind: str
    document_name: str
    document_session_uuid: str
    canonical_path: str | None
    reason: str
    dirty: bool | None
    state: str
    generation: int | None
