"""In-flight worker job state tracked by the manager."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class WorkerInvocation:
    job_id: str
    code: str
    options: dict[str, Any]
    snapshot: dict[str, Any]
    workspace: Path
    completed: threading.Event
    result: dict[str, Any] | None = None
    cancelled: bool = False
