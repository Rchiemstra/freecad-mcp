"""Shared queue and processing state for legacy GUI dispatch."""

from __future__ import annotations

import queue
from typing import Any

rpc_request_queue: queue.Queue[Any] = queue.Queue()
SHUTDOWN = object()
processing = False
processing_since: float = 0.0
waker: Any | None = None
