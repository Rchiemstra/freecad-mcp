"""Serialized worker lane for sync MCP tool bodies."""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..telemetry.context import TelemetryContext, get_context, update_context
from .helpers import worker_context_updates


class SerializedWorkerLane:
    """Single-thread executor that keeps sync tool bodies off the event loop."""

    def __init__(self, *, thread_name_prefix: str) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=thread_name_prefix,
        )

    async def run(self, func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
        parent_ctx = get_context()
        ctx = contextvars.copy_context()
        loop = asyncio.get_running_loop()

        def _invoke() -> tuple[Any, TelemetryContext, BaseException | None]:
            worker_ctx = parent_ctx
            result: Any = None
            exc: BaseException | None = None

            def _run_in_copied_context() -> None:
                nonlocal worker_ctx, result, exc
                try:
                    result = func(*args, **kwargs)
                except BaseException as raised:
                    exc = raised
                finally:
                    worker_ctx = get_context()

            ctx.run(_run_in_copied_context)
            return result, worker_ctx, exc

        result, worker_ctx, exc = await loop.run_in_executor(self._executor, _invoke)
        updates = worker_context_updates(parent_ctx, worker_ctx)
        if updates:
            update_context(**updates)
        if exc is not None:
            raise exc
        return result
