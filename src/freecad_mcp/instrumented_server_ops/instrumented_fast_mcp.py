"""Instrumented FastMCP subclass."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from .serialized_worker_lane import SerializedWorkerLane


class InstrumentedFastMCP(FastMCP):
    task_request_canceller: Callable[[str], Any] | None = None
    post_tool_completed_hook: Callable[[float, str], Any] | None = None
    _sync_worker_lane: SerializedWorkerLane | None = None
    _control_worker_lane: SerializedWorkerLane | None = None
