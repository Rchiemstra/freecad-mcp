"""Inert owner for the add-on gateway's process-wide runtime resources."""

from __future__ import annotations

import threading as _threading
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from functools import partial as _partial

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


def _dispose_dispatcher(component: object) -> None:
    failures: list[BaseException] = []
    for method_name in ("stop_accepting", "deleteLater"):
        method = getattr(component, method_name, None)
        if not callable(method):
            continue
        try:
            method()
        except BaseException as exc:
            failures.append(exc)
    if failures:
        raise BaseExceptionGroup("Dispatcher disposal failed", failures)


def _dispose_worker_manager(component: object) -> None:
    method = getattr(component, "stop", None)
    if callable(method):
        stopped = method(timeout=4.0)
        if stopped is False:
            raise RuntimeError("worker manager did not stop within the disposal timeout")


def _dispose_listener(component: object) -> None:
    method = getattr(component, "server_close", None)
    if callable(method):
        method()


def _cleanup_partial_construction(
    stop_event: object,
    owned_resources: list[tuple[object, _Callable[[], None]]],
    primary_failure: BaseException,
) -> None:
    failures = [primary_failure]
    try:
        stop_event.set()
    except BaseException as exc:
        failures.append(exc)
    for _resource, disposer in reversed(owned_resources):
        try:
            disposer()
        except BaseException as exc:
            failures.append(exc)
    if len(failures) == 1:
        raise primary_failure
    raise BaseExceptionGroup("Addon runtime construction failed", failures)


def _required_component(component: object | None, factory_name: str) -> object:
    if component is None:
        raise ValueError(f"{factory_name} returned None")
    return component


def _register_capability_bridge(listener: object, capability_bridge: object) -> None:
    register_instance = getattr(listener, "register_instance", None)
    if not callable(register_instance):
        raise TypeError("listener must provide register_instance()")
    register_instance(capability_bridge)


def _validated_authentication(
    authentication: object,
    *,
    required: bool,
) -> tuple[object | None, str]:
    if not isinstance(authentication, tuple) or len(authentication) != 2:
        raise TypeError("authentication_factory must return a pair")
    session_manager, warning = authentication
    if required and session_manager is None:
        raise RuntimeError("authenticated session is required")
    return session_manager, str(warning or "")


def _build_addon_runtime(
    *,
    shutdown_requested: object,
    dispatcher_factory: _Callable[[], object],
    worker_manager_factory: _Callable[[object], object | None],
    listener_factory: _Callable[[object, object], object],
    authentication_factory: _Callable[[object, object], tuple[object | None, str]],
    capability_bridge_factory: _Callable[
        [object, object | None, object, object, object, object], object
    ],
    authentication_required: bool,
    request_replay_cache: object,
    inflight_requests: object,
    handoff_continuations: object,
    acquisition_claims: object,
) -> tuple[AddonRuntime, str]:
    """Construct one restart-scoped gateway graph without starting it."""

    factories = (
        dispatcher_factory,
        worker_manager_factory,
        listener_factory,
        authentication_factory,
        capability_bridge_factory,
    )
    if not all(callable(factory) for factory in factories):
        raise TypeError("runtime factories must be callable")
    if not callable(getattr(shutdown_requested, "set", None)):
        raise TypeError("shutdown_requested must provide set()")

    owned_resources: list[tuple[object, _Callable[[], None]]] = []
    try:
        dispatcher = _required_component(dispatcher_factory(), "dispatcher_factory")
        owned_resources.append(
            (dispatcher, _partial(_dispose_dispatcher, dispatcher))
        )

        worker_manager = worker_manager_factory(dispatcher)
        if worker_manager is not None:
            owned_resources.append(
                (
                    worker_manager,
                    _partial(_dispose_worker_manager, worker_manager),
                )
            )

        capability_bridge = _required_component(
            capability_bridge_factory(
                dispatcher,
                worker_manager,
                request_replay_cache,
                inflight_requests,
                handoff_continuations,
                acquisition_claims,
            ),
            "capability_bridge_factory",
        )

        listener = _required_component(
            listener_factory(dispatcher, capability_bridge),
            "listener_factory",
        )
        owned_resources.append((listener, _partial(_dispose_listener, listener)))
        _register_capability_bridge(listener, capability_bridge)

        session_manager, warning = _validated_authentication(
            authentication_factory(listener, request_replay_cache),
            required=authentication_required,
        )

        return (
            AddonRuntime(
                listener=listener,
                dispatcher=dispatcher,
                worker_manager=worker_manager,
                session_manager=session_manager,
                request_replay_cache=request_replay_cache,
                inflight_requests=inflight_requests,
                handoff_continuations=handoff_continuations,
                acquisition_claims=acquisition_claims,
                collaboration_bridge=capability_bridge,
                shutdown_requested=shutdown_requested,
                owned_resources=owned_resources,
            ),
            warning,
        )
    except BaseException as exc:
        _cleanup_partial_construction(shutdown_requested, owned_resources, exc)
