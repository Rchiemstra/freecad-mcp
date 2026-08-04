"""Inert owner for the add-on gateway's process-wide runtime resources."""

from __future__ import annotations

import threading as _threading
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field

__all__ = ["AddonRuntime"]


@_dataclass(frozen=True, slots=True, init=False)
class AddonRuntime:
    """Hold explicitly constructed gateway dependencies without starting them."""

    listener: object | None
    dispatcher: object | None
    worker_manager: object | None
    session_manager: object | None
    request_replay_cache: object | None
    inflight_requests: object | None
    handoff_continuations: object | None
    acquisition_claims: object | None
    collaboration_bridge: object | None
    shutdown_requested: _threading.Event
    _owned_resources: tuple[tuple[object, _Callable[[], None]], ...] = _field(
        repr=False,
        compare=False,
    )
    _dispose_lock: _threading.Lock = _field(repr=False, compare=False)
    _dispose_complete: _threading.Event = _field(repr=False, compare=False)
    _dispose_failures: tuple[BaseException, ...] = _field(
        default=(),
        repr=False,
        compare=False,
    )
    _dispose_owner: int | None = _field(default=None, repr=False, compare=False)
    _disposed: bool = _field(default=False, repr=False, compare=False)

    def __init__(
        self,
        *,
        listener: object | None = None,
        dispatcher: object | None = None,
        worker_manager: object | None = None,
        session_manager: object | None = None,
        request_replay_cache: object | None = None,
        inflight_requests: object | None = None,
        handoff_continuations: object | None = None,
        acquisition_claims: object | None = None,
        collaboration_bridge: object | None = None,
        shutdown_requested: _threading.Event | None = None,
        owned_resources: _Iterable[
            tuple[object, _Callable[[], None]]
        ] = (),
    ) -> None:
        """Store injected identities and validate explicit cleanup ownership."""

        components = (
            listener,
            dispatcher,
            worker_manager,
            session_manager,
            request_replay_cache,
            inflight_requests,
            handoff_continuations,
            acquisition_claims,
            collaboration_bridge,
        )
        owned = tuple(owned_resources)
        seen: set[int] = set()
        for resource, disposer in owned:
            if resource is None:
                raise ValueError("an owned runtime resource cannot be None")
            if all(resource is not component for component in components):
                raise ValueError("an owned resource must be an injected component")
            if id(resource) in seen:
                raise ValueError("a runtime resource may be owned only once")
            if not callable(disposer):
                raise TypeError("a runtime resource disposer must be callable")
            seen.add(id(resource))

        stop_event = (
            _threading.Event() if shutdown_requested is None else shutdown_requested
        )
        if not callable(getattr(stop_event, "set", None)):
            raise TypeError("shutdown_requested must provide set()")

        object.__setattr__(self, "listener", listener)
        object.__setattr__(self, "dispatcher", dispatcher)
        object.__setattr__(self, "worker_manager", worker_manager)
        object.__setattr__(self, "session_manager", session_manager)
        object.__setattr__(self, "request_replay_cache", request_replay_cache)
        object.__setattr__(self, "inflight_requests", inflight_requests)
        object.__setattr__(self, "handoff_continuations", handoff_continuations)
        object.__setattr__(self, "acquisition_claims", acquisition_claims)
        object.__setattr__(self, "collaboration_bridge", collaboration_bridge)
        object.__setattr__(self, "shutdown_requested", stop_event)
        object.__setattr__(self, "_owned_resources", owned)
        object.__setattr__(self, "_dispose_lock", _threading.Lock())
        object.__setattr__(self, "_dispose_complete", _threading.Event())
        object.__setattr__(self, "_dispose_failures", ())
        object.__setattr__(self, "_dispose_owner", None)
        object.__setattr__(self, "_disposed", False)

    @property
    def disposed(self) -> bool:
        """Return whether this runtime has already won disposal ownership."""

        with self._dispose_lock:
            return self._disposed

    def dispose(self) -> None:
        """Signal shutdown and release explicitly owned resources exactly once."""

        with self._dispose_lock:
            if self._disposed:
                if (
                    self._dispose_owner == _threading.get_ident()
                    and not self._dispose_complete.is_set()
                ):
                    return
                owns_disposal = False
            else:
                object.__setattr__(self, "_disposed", True)
                object.__setattr__(self, "_dispose_owner", _threading.get_ident())
                owns_disposal = True

        if not owns_disposal:
            self._dispose_complete.wait()
            with self._dispose_lock:
                failures = self._dispose_failures
            if failures:
                raise BaseExceptionGroup("AddonRuntime disposal failed", failures)
            return

        failures: list[BaseException] = []
        try:
            self.shutdown_requested.set()
        except BaseException as exc:
            failures.append(exc)
        for _resource, disposer in reversed(self._owned_resources):
            try:
                disposer()
            except BaseException as exc:
                failures.append(exc)
        with self._dispose_lock:
            object.__setattr__(self, "_dispose_failures", tuple(failures))
            object.__setattr__(self, "_dispose_owner", None)
            self._dispose_complete.set()
        if failures:
            raise BaseExceptionGroup("AddonRuntime disposal failed", failures)
