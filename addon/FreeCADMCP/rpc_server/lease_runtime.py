"""Process-lifetime document lease runtime helpers."""

from __future__ import annotations

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


def _rpc_mod():
    from . import rpc_server as rpc_mod

    return rpc_mod


def initialize_document_lease_runtime(settings=None):
    return _initialize_document_lease_runtime_impl(
        settings=settings, rpc_mod=_rpc_mod()
    )


def shutdown_document_lease_runtime(timeout=3.0):
    return _shutdown_document_lease_runtime_impl(timeout=timeout, rpc_mod=_rpc_mod())


def _lease_watchdog_loop(interval_seconds=2.0, stop_event=None):
    return lease_watchdog_loop(
        interval_seconds, stop_event, rpc_mod=_rpc_mod()
    )


def _ensure_lease_watchdog_running(interval_seconds=2.0):
    return ensure_lease_watchdog_running(interval_seconds, rpc_mod=_rpc_mod())


def _utc_timestamp(value):
    return utc_timestamp(value)


def _process_started_at():
    rpc_mod = _rpc_mod()
    return process_started_at(addon_loaded_at=rpc_mod.addon_loaded_at, rpc_mod=rpc_mod)


def _boot_identity():
    return _rpc_mod()._trusted_boot_identity()


def _trusted_boot_identity():
    return trusted_boot_identity(rpc_mod=_rpc_mod())


def _probe_process_liveness(pid):
    return probe_process_liveness(pid, rpc_mod=_rpc_mod())


def _make_local_runtime_identity(settings, lease=None):
    return make_local_runtime_identity(settings, lease, rpc_mod=_rpc_mod())


def _require_authenticated_lease_runtime(profile_id):
    return require_authenticated_lease_runtime(profile_id, rpc_mod=_rpc_mod())


def _profile_fingerprint():
    return profile_fingerprint(rpc_mod=_rpc_mod())


def _import_document_lock():
    return import_document_lock()


def _import_document_lease():
    return import_document_lease()


__all__ = [
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
