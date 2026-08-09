"""Dispose the single composed RPC runtime without touching document authority."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("FreeCADMCP.rpc_server")
_compatibility_stop: Callable[..., str] | None = None


def bind_stop_rpc_server_compatibility(callback: Callable[..., str]) -> None:
    """Bind the old defining path to the composition-root stop operation."""

    global _compatibility_stop
    if not callable(callback):
        raise TypeError("stop compatibility callback must be callable")
    _compatibility_stop = callback


@dataclass(slots=True)
class _RuntimeShutdownClaim:
    runtime: Any
    listener_thread: Any = None
    completed: threading.Event = field(default_factory=threading.Event)
    failure: BaseException | None = None
    preflight_failures: list[BaseException] = field(default_factory=list)


def _fence_inflight_cancellations(
    runtime: Any,
    timeout: float,
) -> list[BaseException]:
    failures: list[BaseException] = []
    registry = runtime.inflight_requests
    cancelling_rpc = runtime.collaboration_bridge
    if registry is None or cancelling_rpc is None:
        return failures
    cancellation_deadline = time.monotonic() + timeout
    try:
        inflight_requests = registry.request_cancel_all()
    except BaseException as exc:
        logger.exception("Could not request cancellation during RPC shutdown")
        failures.append(exc)
        return failures
    for inflight in inflight_requests:
        try:
            remaining = max(0.0, cancellation_deadline - time.monotonic())
            fenced = cancelling_rpc._begin_request_cancellation(
                inflight, wait_timeout=remaining
            )
            if fenced is None:
                logger.error(
                    "Cancellation fence for request %s remains owned by "
                    "another phase; its active lease/error fence is retained",
                    inflight.request_id,
                )
        except BaseException as exc:
            logger.exception(
                "Could not fence request %s during RPC shutdown",
                inflight.request_id,
            )
            failures.append(exc)
    return failures


def _invoke_optional(component: Any, method_name: str) -> None:
    method = getattr(component, method_name, None)
    if callable(method):
        method()


def _stop_listener(listener: Any, failures: list[BaseException]) -> None:
    if listener is None:
        return
    for method_name in ("begin_shutdown", "shutdown"):
        try:
            _invoke_optional(listener, method_name)
        except BaseException as exc:
            failures.append(exc)


def _begin_worker_shutdown(
    worker_manager: Any,
    failures: list[BaseException],
) -> None:
    if worker_manager is None:
        return
    try:
        _invoke_optional(worker_manager, "_begin_shutdown")
    except BaseException as exc:
        failures.append(exc)


def _join_listener_thread(
    listener_thread: Any,
    failures: list[BaseException],
) -> None:
    if listener_thread is None or listener_thread is threading.current_thread():
        return
    join = getattr(listener_thread, "join", None)
    if not callable(join):
        return
    try:
        join(timeout=2.0)
        is_alive = getattr(listener_thread, "is_alive", None)
        if callable(is_alive) and is_alive():
            failures.append(
                RuntimeError(
                    "RPC listener thread did not stop within the shutdown timeout"
                )
            )
    except BaseException as exc:
        failures.append(exc)


def _unpublish_disposed_runtime(
    rpc_mod: Any,
    runtime: Any,
    claim: _RuntimeShutdownClaim,
    failures: list[BaseException],
) -> None:
    if failures:
        return
    from .server_lifecycle import _unpublish_runtime

    with rpc_mod._runtime_lifecycle_lock:
        _unpublish_runtime(rpc_mod, runtime)
        if rpc_mod._runtime_shutdown_claim is claim:
            rpc_mod._runtime_shutdown_claim = None


def _dispose_claimed_runtime(
    rpc_mod: Any,
    runtime: Any,
    listener_thread: Any,
    claim: _RuntimeShutdownClaim,
) -> None:
    failures: list[BaseException] = list(claim.preflight_failures)
    _stop_listener(runtime.listener, failures)
    _begin_worker_shutdown(runtime.worker_manager, failures)
    _join_listener_thread(listener_thread, failures)
    try:
        runtime.dispose()
    except BaseException as exc:
        failures.append(exc)
    try:
        _unpublish_disposed_runtime(rpc_mod, runtime, claim, failures)
    except BaseException as exc:
        failures.append(exc)
    finally:
        if failures:
            claim.failure = BaseExceptionGroup(
                "RPC runtime shutdown failed",
                failures,
            )
            logger.error("RPC runtime shutdown failed: %s", claim.failure)
        claim.completed.set()


def _start_runtime_disposal(
    rpc_mod: Any,
    runtime: Any,
    listener_thread: Any,
    claim: _RuntimeShutdownClaim,
) -> None:
    try:
        cleanup_thread = threading.Thread(
            target=_dispose_claimed_runtime,
            args=(rpc_mod, runtime, listener_thread, claim),
            daemon=True,
        )
        cleanup_thread.start()
    except BaseException:
        logger.exception("Could not construct or start RPC runtime disposal thread")
        _dispose_claimed_runtime(rpc_mod, runtime, listener_thread, claim)


def stop_rpc_server(
    *,
    dependencies: Any | None = None,
    wait_for_completion: bool = False,
):
    """Stop the runtime bound explicitly by the composition root."""

    if dependencies is None:
        if _compatibility_stop is None:
            raise RuntimeError("RPC stop composition root is not initialized")
        if wait_for_completion:
            return _compatibility_stop(wait_for_completion=True)
        return _compatibility_stop()
    rpc_mod = dependencies
    owns_shutdown = False
    with rpc_mod._runtime_lifecycle_lock:
        claim = rpc_mod._runtime_shutdown_claim
        if claim is None:
            runtime = rpc_mod._addon_runtime
            if runtime is None or getattr(runtime, "disposed", False):
                return "RPC Server was not running."
            listener_thread = getattr(runtime, "listener_thread", None)
            claim = _RuntimeShutdownClaim(
                runtime,
                listener_thread=listener_thread,
            )
            rpc_mod._runtime_shutdown_claim = claim
            owns_shutdown = True
        else:
            runtime = claim.runtime
            listener_thread = None

    if owns_shutdown:
        try:
            runtime.shutdown_requested.set()
        except BaseException as exc:
            claim.preflight_failures.append(exc)
        claim.preflight_failures.extend(
            _fence_inflight_cancellations(
                runtime,
                rpc_mod.RPC_SHUTDOWN_CANCELLATION_WAIT_SECONDS,
            )
        )
        _start_runtime_disposal(rpc_mod, runtime, listener_thread, claim)

    completed = claim.completed.wait(
        timeout=None if wait_for_completion else 2.5
    )
    if completed:
        if claim.failure is not None:
            return f"RPC Server shutdown failed: {claim.failure}"
        logger.info("RPC Server stopped")
        return "RPC Server stopped."
    return "RPC Server shutdown is continuing in the background."
