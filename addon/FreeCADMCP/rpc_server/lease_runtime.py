"""Process-lifetime document lease runtime helpers."""

from __future__ import annotations

import os
import platform
import sys
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .lease_runtime_ops.boot_identity import trusted_boot_identity
from .lease_runtime_ops.imports import import_document_lease, import_document_lock
from .lease_runtime_ops.initialize import (
    initialize_document_lease_runtime as _initialize_document_lease_runtime_impl,
)
from .lease_runtime_ops.process_liveness import (
    make_local_runtime_identity,
    probe_process_liveness,
    process_started_at,
    profile_fingerprint,
    require_authenticated_lease_runtime,
)
from .lease_runtime_ops.timestamps import utc_timestamp
from .lease_runtime_ops.watchdog import (
    ensure_lease_watchdog_running,
    lease_watchdog_loop,
)
from .lease_runtime_ops.watchdog import (
    shutdown_document_lease_runtime as _shutdown_document_lease_runtime_impl,
)
from .settings import load_settings


@dataclass(slots=True)
class LeaseRuntimeDependencies:
    """Concrete process-lifetime state used by the legacy lease compatibility seam."""

    ensure_v2_document: Any = lambda document: document
    document_identity_service: Any = None
    document_lease_service: Any = None
    document_lease_service_provider: Callable[[], Any] | None = None
    document_lease_runtime_policy: Any = None
    document_lease_runtime_mode: Any = None
    save_service: Any = None
    rpc_request_replay_cache: Any = None
    lease_watchdog_thread: Any = None
    lease_watchdog_stop: threading.Event = field(default_factory=threading.Event)
    lease_watchdog_lock: threading.RLock = field(default_factory=threading.RLock)
    addon_loaded_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    addon_runtime_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    runtime_id: str = ""
    os: Any = os
    sys: Any = sys
    platform: Any = platform
    Path: Any = Path
    load_settings: Any = load_settings
    ensure_watchdog_callback: Any = None
    watchdog_loop_callback: Any = None
    probe_process_liveness_callback: Any = None
    trusted_boot_identity_callback: Any = None
    profile_fingerprint_callback: Any = None
    service_process_liveness_probe: Any = None

    @property
    def _ADDON_RUNTIME_ID(self) -> str:
        return self.addon_runtime_id

    @property
    def rpc_server_runtime_id(self) -> str:
        return self.runtime_id or self.addon_runtime_id

    def _ensure_v2_document(self, document):
        return self.ensure_v2_document(document)

    def _current_document_lease_service(self):
        if self.document_lease_service_provider is not None:
            return self.document_lease_service_provider()
        return self.document_lease_service

    def _import_document_lock(self):
        return import_document_lock()

    def _import_document_lease(self):
        return import_document_lease()

    def _lease_watchdog_loop(self, interval_seconds=2.0, stop_event=None):
        if self.watchdog_loop_callback is not None:
            return self.watchdog_loop_callback(interval_seconds, stop_event)
        return lease_watchdog_loop(interval_seconds, stop_event, rpc_mod=self)

    def _ensure_lease_watchdog_running(self, interval_seconds=2.0):
        if self.ensure_watchdog_callback is not None:
            if float(interval_seconds) == 2.0:
                return self.ensure_watchdog_callback()
            return self.ensure_watchdog_callback(interval_seconds)
        return ensure_lease_watchdog_running(interval_seconds, rpc_mod=self)

    def _profile_fingerprint(self):
        if self.profile_fingerprint_callback is not None:
            return self.profile_fingerprint_callback()
        return profile_fingerprint(rpc_mod=self)

    def _probe_process_liveness(self, pid):
        if self.probe_process_liveness_callback is not None:
            return self.probe_process_liveness_callback(pid)
        return probe_process_liveness(pid, rpc_mod=self)

    def _boot_identity(self):
        if self.trusted_boot_identity_callback is not None:
            return self.trusted_boot_identity_callback()
        return trusted_boot_identity(rpc_mod=self)

    def _make_local_runtime_identity(self, settings, lease=None):
        return make_local_runtime_identity(settings, lease, rpc_mod=self)


@dataclass(frozen=True, slots=True)
class LeaseRuntimeCompatibility:
    """Narrow old-path operations bound to the sole composition-root state."""

    initialize: Callable[..., Any]
    shutdown: Callable[..., Any]
    watchdog_loop: Callable[..., Any]
    ensure_watchdog: Callable[..., Any]
    process_started_at: Callable[..., Any]
    boot_identity: Callable[..., Any]
    trusted_boot_identity: Callable[..., Any]
    probe_process_liveness: Callable[..., Any]
    make_local_runtime_identity: Callable[..., Any]
    require_authenticated_runtime: Callable[..., Any]
    profile_fingerprint: Callable[..., Any]


_compatibility_operations: LeaseRuntimeCompatibility | None = None


def bind_lease_runtime_compatibility(
    operations: LeaseRuntimeCompatibility,
) -> None:
    """Bind the historic defining path to explicit root operations."""

    global _compatibility_operations
    if not isinstance(operations, LeaseRuntimeCompatibility):
        raise TypeError("operations must be LeaseRuntimeCompatibility")
    _compatibility_operations = operations


def _compatibility() -> LeaseRuntimeCompatibility:
    operations = _compatibility_operations
    if operations is None:
        raise RuntimeError("lease runtime composition root is not initialized")
    return operations


def _dependencies(explicit: LeaseRuntimeDependencies | None) -> LeaseRuntimeDependencies:
    if explicit is None:
        raise RuntimeError("explicit lease runtime dependencies are required")
    if not isinstance(explicit, LeaseRuntimeDependencies):
        raise TypeError("dependencies must be LeaseRuntimeDependencies")
    return explicit


def initialize_document_lease_runtime(settings=None, *, dependencies=None):
    if dependencies is None:
        return _compatibility().initialize(settings)
    return _initialize_document_lease_runtime_impl(
        settings=settings, rpc_mod=_dependencies(dependencies)
    )


def shutdown_document_lease_runtime(timeout=3.0, *, dependencies=None):
    if dependencies is None:
        return _compatibility().shutdown(timeout)
    return _shutdown_document_lease_runtime_impl(
        timeout=timeout, rpc_mod=_dependencies(dependencies)
    )


def _lease_watchdog_loop(interval_seconds=2.0, stop_event=None, *, dependencies=None):
    if dependencies is None:
        return _compatibility().watchdog_loop(interval_seconds, stop_event)
    return lease_watchdog_loop(
        interval_seconds, stop_event, rpc_mod=_dependencies(dependencies)
    )


def _ensure_lease_watchdog_running(interval_seconds=2.0, *, dependencies=None):
    if dependencies is None:
        return _compatibility().ensure_watchdog(interval_seconds)
    return ensure_lease_watchdog_running(
        interval_seconds, rpc_mod=_dependencies(dependencies)
    )


def _utc_timestamp(value):
    return utc_timestamp(value)


def _process_started_at(*, dependencies=None):
    if dependencies is None:
        return _compatibility().process_started_at()
    rpc_mod = _dependencies(dependencies)
    return process_started_at(addon_loaded_at=rpc_mod.addon_loaded_at, rpc_mod=rpc_mod)


def _boot_identity(*, dependencies=None):
    if dependencies is None:
        return _compatibility().boot_identity()
    return _dependencies(dependencies)._boot_identity()


def _trusted_boot_identity(*, dependencies=None):
    if dependencies is None:
        return _compatibility().trusted_boot_identity()
    return trusted_boot_identity(rpc_mod=_dependencies(dependencies))


def _probe_process_liveness(pid, *, dependencies=None):
    if dependencies is None:
        return _compatibility().probe_process_liveness(pid)
    return probe_process_liveness(pid, rpc_mod=_dependencies(dependencies))


def _make_local_runtime_identity(settings, lease=None, *, dependencies=None):
    if dependencies is None:
        return _compatibility().make_local_runtime_identity(settings, lease)
    return make_local_runtime_identity(
        settings, lease, rpc_mod=_dependencies(dependencies)
    )


def _require_authenticated_lease_runtime(profile_id, *, dependencies=None):
    if dependencies is None:
        return _compatibility().require_authenticated_runtime(profile_id)
    return require_authenticated_lease_runtime(
        profile_id, rpc_mod=_dependencies(dependencies)
    )


def _profile_fingerprint(*, dependencies=None):
    if dependencies is None:
        return _compatibility().profile_fingerprint()
    return profile_fingerprint(rpc_mod=_dependencies(dependencies))


def _import_document_lock():
    return import_document_lock()


def _import_document_lease():
    return import_document_lease()


__all__ = [
    "LeaseRuntimeDependencies",
    "_boot_identity",
    "_ensure_lease_watchdog_running",
    "_import_document_lease",
    "_import_document_lock",
    "_lease_watchdog_loop",
    "_make_local_runtime_identity",
    "_probe_process_liveness",
    "_process_started_at",
    "_profile_fingerprint",
    "_require_authenticated_lease_runtime",
    "_trusted_boot_identity",
    "_utc_timestamp",
    "initialize_document_lease_runtime",
    "shutdown_document_lease_runtime",
]
