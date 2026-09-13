"""JSON-RPC listener start orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import FreeCAD

logger = logging.getLogger("FreeCADMCP.rpc_server")
_compatibility_start: Callable[[Any], str] | None = None


def bind_start_rpc_server_compatibility(callback: Callable[[Any], str]) -> None:
    """Bind the old defining path to the composition-root start operation."""

    global _compatibility_start
    if not callable(callback):
        raise TypeError("start compatibility callback must be callable")
    _compatibility_start = callback


class _StartRuntimeBindings:
    """Own restart-scoped candidates until one ``AddonRuntime`` is published."""

    _LOCAL_NAMES = frozenset(
        {
            "shutdown_requested",
            "rpc_request_replay_cache",
            "rpc_inflight_request_registry",
            "rpc_session_manager",
            "rpc_runtime_manifest",
            "rpc_server_instance",
            "rpc_server_thread",
            "gui_dispatcher",
            "worker_manager",
            "rpc_server_runtime_id",
            "rpc_server_started_at",
            "rpc_server_actual_endpoint",
        }
    )

    def __init__(self, root: Any, *, request_replay_cache: Any | None = None) -> None:
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "shutdown_requested", root.ShutdownEvent())
        object.__setattr__(
            self,
            "rpc_request_replay_cache",
            (
                root.RequestReplayCache()
                if request_replay_cache is None
                else request_replay_cache
            ),
        )
        object.__setattr__(
            self, "rpc_inflight_request_registry", root.InflightRequestRegistry()
        )
        object.__setattr__(self, "rpc_session_manager", None)
        object.__setattr__(self, "rpc_runtime_manifest", None)
        object.__setattr__(self, "rpc_server_instance", None)
        object.__setattr__(self, "rpc_server_thread", None)
        object.__setattr__(self, "gui_dispatcher", None)
        object.__setattr__(self, "worker_manager", None)
        object.__setattr__(self, "rpc_server_runtime_id", root._ADDON_RUNTIME_ID)
        object.__setattr__(self, "rpc_server_started_at", "")
        object.__setattr__(self, "rpc_server_actual_endpoint", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_root"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._LOCAL_NAMES:
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, "_root"), name, value)

def _gui_thread_parent(rpc_mod: Any) -> tuple[Any, str | None]:
    app = rpc_mod.QtWidgets.QApplication.instance()
    if app is None:
        return None, "RPC Server could not start: no Qt application is running."
    if rpc_mod.QtCore.QThread.currentThread() != app.thread():
        return None, "RPC Server must be started from FreeCAD's GUI thread."
    try:
        return rpc_mod.FreeCADGui.getMainWindow(), None
    except Exception:
        return None, None


def _resolve_port(port: Any, settings: dict[str, Any]) -> int:
    if port is not None:
        return int(port)
    try:
        return int(settings.get("rpc_port", 9875))
    except (TypeError, ValueError):
        return 9875


def _build_worker_manager(rpc_mod: Any, settings: dict[str, Any]) -> Any:
    version = tuple(rpc_mod._freecad_version_parts()[:4])
    while len(version) < 4:
        version += ("",)
    return rpc_mod.WorkerManager(
        rpc_mod.WorkerRuntime(
            gui_executable=rpc_mod.sys.executable,
            freecad_home=(
                FreeCAD.getHomePath()
                if callable(getattr(FreeCAD, "getHomePath", None))
                else rpc_mod.os.path.dirname(rpc_mod.sys.executable)
            ),
            gui_version=version,
            configured_path=settings.get("freecadcmd_path", ""),
        ),
        rpc_mod.os.path.dirname(__file__), autostart=False,
    )


def _start_runtime_components(
    rpc_mod: Any,
    *,
    actual_host: str,
    actual_port: int,
    remote_enabled: bool,
    allowed_ips: str,
    runtime: Any,
) -> tuple[Any, Any, Any]:
    if runtime is None:
        raise RuntimeError("RPC runtime was not composed before listener launch")
    start_worker = getattr(runtime.worker_manager, "_start", None)
    if callable(start_worker):
        start_worker()

    publication_ready = rpc_mod.threading.Event()
    publication_abandoned = rpc_mod.threading.Event()

    def server_loop():
        publication_ready.wait()
        if publication_abandoned.is_set():
            return
        logger.info("RPC Server started at %s:%s", actual_host, actual_port)
        if remote_enabled:
            logger.info("Remote connections enabled. Allowed IPs: %s", allowed_ips)
        runtime.listener.serve_forever()

    listener_thread = rpc_mod.threading.Thread(target=server_loop, daemon=True)
    listener_thread.start()
    return listener_thread, publication_ready, publication_abandoned


def start_rpc_server(port=None, *, dependencies: Any | None = None):
    """Start through bindings supplied explicitly by the composition root."""

    if dependencies is None:
        if _compatibility_start is None:
            raise RuntimeError("RPC start composition root is not initialized")
        return _compatibility_start(port)

    try:
        from ..runtime import _build_addon_runtime
    except ImportError:  # pragma: no cover - flat addon import path
        from runtime import _build_addon_runtime
    from .server_lifecycle_ops.abort_start import abort_rpc_start
    from .server_lifecycle_ops.start_gates import (
        refuse_enforce_without_profile,
    )
    from .server_lifecycle_ops.v2_session import initialize_rpc_v2_session

    with dependencies._runtime_lifecycle_lock:
        return _start_rpc_server_locked(
            _build_addon_runtime,
            dependencies,
            port=port,
            abort_rpc_start=abort_rpc_start,
            refuse_enforce_without_profile=refuse_enforce_without_profile,
            initialize_rpc_v2_session=initialize_rpc_v2_session,
        )


def _start_rpc_server_locked(
    builder,
    rpc_mod: Any,
    *,
    port,
    abort_rpc_start,
    refuse_enforce_without_profile,
    initialize_rpc_v2_session,
):
    if rpc_mod._runtime_shutdown_claim is not None:
        return "RPC Server shutdown is still in progress."
    previous_runtime = rpc_mod._addon_runtime
    if previous_runtime is not None and not previous_runtime.disposed:
        return "RPC Server already running."

    replay_cache = (
        previous_runtime.request_replay_cache
        if previous_runtime is not None
        else None
    )
    rpc_mod = _StartRuntimeBindings(
        rpc_mod,
        request_replay_cache=replay_cache,
    )

    parent, thread_error = _gui_thread_parent(rpc_mod)
    if thread_error is not None:
        return thread_error

    settings = rpc_mod.load_settings()
    configuration_error = settings.get("_configuration_error")
    if configuration_error:
        abort_rpc_start(rpc_mod)
        return (
            "RPC Server refused invalid freecad_mcp_settings.json: "
            f"{configuration_error}"
        )

    port = _resolve_port(port, settings)
    rpc_mod.configure_parts_library_path(FreeCAD.getUserAppDataDir())
    remote_enabled = bool(settings.get("remote_enabled", False))
    allowed_ips = str(settings.get("allowed_ips", "127.0.0.1"))

    authentication_mode = str(settings.get("document_lease_mode", "off"))
    profile_id = str(
        settings.get("profile_instance_id") or settings.get("instance_id") or ""
    )
    auth_secret_file = str(settings.get("auth_secret_file") or "")

    enforce_error = refuse_enforce_without_profile(
        rpc_mod,
        authentication_mode=authentication_mode,
        profile_id=profile_id,
        auth_secret_file=auth_secret_file,
    )
    if enforce_error is not None:
        return enforce_error

    try:
        rpc_v2_initialization_warning, actual_host, actual_port = (
            _construct_and_launch_runtime(
                builder,
                rpc_mod,
                parent=parent,
                settings=settings,
                port=port,
                allowed_ips=allowed_ips,
                remote_enabled=remote_enabled,
                authentication_mode=authentication_mode,
                profile_id=profile_id,
                auth_secret_file=auth_secret_file,
                initialize_rpc_v2_session=initialize_rpc_v2_session,
            )
        )
    except _RpcStartRefusal as exc:
        abort_rpc_start(rpc_mod)
        return str(exc)

    msg = f"RPC Server started at {actual_host}:{actual_port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    msg += rpc_v2_initialization_warning
    return msg


class _RpcStartRefusal(RuntimeError):
    """Expected configuration refusal with an already-public-safe message."""


@dataclass(slots=True)
class _FailedRuntimeResources:
    """Retain resources whose construction rollback did not complete."""

    shutdown_requested: Any
    resources: tuple[tuple[Any, Callable[[], None]], ...]
    request_replay_cache: Any
    disposed: bool = True

    @property
    def disposal_retryable(self) -> bool:
        return bool(self.resources)

    def dispose(self) -> None:
        failures: list[BaseException] = []
        retained: list[tuple[Any, Callable[[], None]]] = []
        try:
            self.shutdown_requested.set()
        except BaseException as exc:
            failures.append(exc)
        for resource, disposer in self.resources:
            try:
                disposer()
            except BaseException as exc:
                failures.append(exc)
                retained.append((resource, disposer))
        self.resources = tuple(retained)
        if failures:
            raise BaseExceptionGroup(
                "Failed runtime resource disposal failed",
                failures,
            )


@dataclass(slots=True)
class _FailedRuntimeStartClaim:
    """Fail-closed claim shared with the regular shutdown gate."""

    runtime: Any
    failure: BaseException
    listener_thread: Any = None
    completed: Any = field(default=None)


def _retain_failed_start(rpc_mod: Any, runtime: Any, failure: BaseException) -> None:
    root = getattr(rpc_mod, "_root", rpc_mod)
    completed = root.threading.Event()
    completed.set()
    root._runtime_shutdown_claim = _FailedRuntimeStartClaim(
        runtime=runtime,
        failure=failure,
        listener_thread=getattr(runtime, "listener_thread", None),
        completed=completed,
    )


def _retain_failed_construction(rpc_mod: Any, failure: BaseException) -> bool:
    resources = getattr(failure, "failed_runtime_resources", ())
    shutdown_requested = getattr(failure, "failed_shutdown_event", None)
    if not resources and shutdown_requested is None:
        return False
    retained = _FailedRuntimeResources(
        shutdown_requested=shutdown_requested,
        resources=tuple(resources),
        request_replay_cache=rpc_mod.rpc_request_replay_cache,
    )
    _retain_failed_start(rpc_mod, retained, failure)
    return True


class _UnpublishedRpcFacade:
    """Stage initializer writes locally until the complete graph is published."""

    def __init__(self, source: Any, replay_cache: Any) -> None:
        object.__setattr__(self, "_source", source)
        object.__setattr__(
            self,
            "_values",
            {
                "rpc_session_manager": None,
                "rpc_runtime_manifest": None,
                "rpc_request_replay_cache": replay_cache,
            },
        )

    def __getattr__(self, name: str) -> Any:
        values = object.__getattribute__(self, "_values")
        if name in values:
            return values[name]
        return getattr(object.__getattribute__(self, "_source"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        object.__getattribute__(self, "_values")[name] = value

    def staged(self, name: str) -> Any:
        return object.__getattribute__(self, "_values").get(name)

    def apply_deferred(self) -> None:
        return None


def _bind_authenticated_collaboration_manifest(bridge, manifest) -> None:
    if manifest is None:
        return
    if bridge is None:
        raise RuntimeError("authenticated runtime has no capability bridge")
    bridge._bind_collaboration_runtime_manifest(manifest)


def _bind_authenticated_request_runtime(
    bridge,
    *,
    session_manager,
    manifest,
    actual_endpoint,
    server_started_at,
) -> None:
    if bridge is None:
        raise RuntimeError("authenticated runtime has no capability bridge")
    bridge._bind_authenticated_execution_runtime(
        session_manager=session_manager,
        runtime_manifest=manifest,
        actual_endpoint=actual_endpoint,
        server_started_at=server_started_at,
    )


def _compose_runtime(
    builder,
    rpc_mod: Any,
    *,
    parent: Any,
    settings: dict[str, Any],
    port: int,
    allowed_ips: str,
    remote_enabled: bool,
    authentication_mode: str,
    profile_id: str,
    auth_secret_file: str,
    initialize_rpc_v2_session,
):
    authentication_state: dict[str, Any] = {
        "manifest": None,
        "apply_deferred": lambda: None,
        "actual_host": None,
        "actual_port": None,
        "actual_endpoint": None,
        "server_started_at": None,
    }
    capability_bridge_state: dict[str, Any] = {"bridge": None}

    def dispatcher_factory():
        return rpc_mod.GuiDispatcher(parent)

    def worker_manager_factory(_dispatcher):
        return _build_worker_manager(rpc_mod, settings)

    def capability_bridge_factory(
        _dispatcher,
        _worker_manager,
        _request_replay_cache,
        _inflight_requests,
    ):
        collaboration_collaborators = rpc_mod._build_collaboration_collaborators(
            runtime_manifest=None,
            inflight_request_registry=_inflight_requests,
            request_replay_cache=_request_replay_cache,
            runtime_id=rpc_mod.rpc_server_runtime_id,
        )
        cad_collaborators = rpc_mod._build_cad_collaborators(
            compatibility_api=collaboration_collaborators.compatibility_api
        )
        bridge = rpc_mod.FreeCADRPC(
            allow_execute_code=(
                not remote_enabled
                or bool(settings.get("allow_remote_execute_code", False))
            ),
            collaboration_collaborators=collaboration_collaborators,
            cad_collaborators=cad_collaborators,
            gui_collaborators=rpc_mod._build_gui_collaborators(),
            execution_collaborators=rpc_mod._build_execution_collaborators(
                compatibility_api=collaboration_collaborators.compatibility_api,
                gui_dispatcher_value=_dispatcher,
                worker_manager_value=_worker_manager,
                shutdown_requested_value=rpc_mod.shutdown_requested,
                request_replay_cache=_request_replay_cache,
                inflight_request_registry=_inflight_requests,
                session_manager_value=None,
                runtime_manifest_value=None,
                actual_endpoint_value=None,
                runtime_id_value=rpc_mod.rpc_server_runtime_id,
                server_started_at_value="",
            ),
            lifecycle_collaborators=rpc_mod._build_lifecycle_collaborators(),
        )
        capability_bridge_state["bridge"] = bridge
        return bridge

    def listener_factory(_dispatcher, _capability_bridge):
        try:
            host = rpc_mod.resolve_rpc_bind_host(settings)
        except rpc_mod.SettingsPolicyError as exc:
            raise _RpcStartRefusal(
                f"RPC Server refused unsafe configuration: {exc}"
            ) from exc
        return rpc_mod.FilteredXMLRPCServer(
            (host, port),
            allowed_ips_str=allowed_ips,
            allow_none=True,
            logRequests=False,
        )

    def authentication_factory(listener, request_replay_cache):
        if request_replay_cache is not rpc_mod.rpc_request_replay_cache:
            raise RuntimeError("composition received a different replay cache")
        actual_host, actual_port = listener.server_address[:2]
        authentication_state["actual_host"] = str(actual_host)
        authentication_state["actual_port"] = int(actual_port)
        staged_rpc = _UnpublishedRpcFacade(rpc_mod, request_replay_cache)
        warning = initialize_rpc_v2_session(
            staged_rpc,
            profile_id=profile_id,
            auth_secret_file=auth_secret_file,
            authentication_mode=authentication_mode,
            actual_host=str(actual_host),
            actual_port=int(actual_port),
        )
        if warning.startswith("RPC Server could not"):
            raise _RpcStartRefusal(warning)
        manifest = staged_rpc.staged("rpc_runtime_manifest")
        session_manager = staged_rpc.staged("rpc_session_manager")
        actual_endpoint = {"host": str(actual_host), "port": int(actual_port)}
        server_started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        authentication_state["manifest"] = manifest
        authentication_state["actual_endpoint"] = actual_endpoint
        authentication_state["server_started_at"] = server_started_at
        _bind_authenticated_collaboration_manifest(
            capability_bridge_state["bridge"], manifest
        )
        _bind_authenticated_request_runtime(
            capability_bridge_state["bridge"],
            session_manager=session_manager,
            manifest=manifest,
            actual_endpoint=actual_endpoint,
            server_started_at=server_started_at,
        )
        authentication_state["apply_deferred"] = staged_rpc.apply_deferred
        return session_manager, warning

    runtime, warning = builder(
        shutdown_requested=rpc_mod.shutdown_requested,
        dispatcher_factory=dispatcher_factory,
        worker_manager_factory=worker_manager_factory,
        listener_factory=listener_factory,
        authentication_factory=authentication_factory,
        capability_bridge_factory=capability_bridge_factory,
        authentication_required=(authentication_mode == "enforce"),
        request_replay_cache=rpc_mod.rpc_request_replay_cache,
        inflight_requests=rpc_mod.rpc_inflight_request_registry,
    )
    return (
        runtime,
        warning,
        authentication_state["manifest"],
        authentication_state["apply_deferred"],
        authentication_state["actual_host"],
        authentication_state["actual_port"],
        authentication_state["actual_endpoint"],
        authentication_state["server_started_at"],
    )


def _join_failed_listener(listener_thread: Any) -> list[BaseException]:
    failures: list[BaseException] = []
    if listener_thread is None:
        return failures
    join = getattr(listener_thread, "join", None)
    if not callable(join):
        return failures
    try:
        join(timeout=2.0)
        is_alive = getattr(listener_thread, "is_alive", None)
        if callable(is_alive) and is_alive():
            failures.append(RuntimeError("failed startup listener thread did not stop"))
    except BaseException as exc:
        failures.append(exc)
    return failures


def _cleanup_failed_launch(
    rpc_mod: Any,
    runtime: Any,
    failure: BaseException,
    *,
    listener_thread: Any,
    publication_ready: Any,
    publication_abandoned: Any,
) -> BaseExceptionGroup | None:
    if publication_abandoned is not None:
        publication_abandoned.set()
    if publication_ready is not None:
        publication_ready.set()
    cleanup_failures = _join_failed_listener(listener_thread)
    try:
        runtime.dispose()
    except BaseException as cleanup_exc:
        cleanup_failures.append(cleanup_exc)
        logger.exception("Could not fully dispose failed RPC runtime")
    if not cleanup_failures:
        _unpublish_runtime(rpc_mod, runtime)
        return None
    combined_failure = BaseExceptionGroup(
        "RPC runtime launch and cleanup failed",
        (failure, *cleanup_failures),
    )
    _retain_failed_start(rpc_mod, runtime, combined_failure)
    return combined_failure


def _construct_and_launch_runtime(
    builder,
    rpc_mod: Any,
    **composition,
):
    try:
        (
            runtime,
            warning,
            runtime_manifest,
            apply_deferred,
            actual_host,
            actual_port,
            actual_endpoint,
            server_started_at,
        ) = (
            _compose_runtime(
                builder,
                rpc_mod,
                **composition,
            )
        )
    except _RpcStartRefusal:
        raise
    except BaseException as exc:
        logger.error("Could not construct RPC runtime: %s", exc)
        _retain_failed_construction(rpc_mod, exc)
        if not isinstance(exc, Exception):
            raise
        raise _RpcStartRefusal(
            "RPC Server could not construct its runtime: "
            f"{rpc_mod._redact_rpc_diagnostic(exc)}"
        ) from exc

    listener_thread = None
    publication_ready = None
    publication_abandoned = None
    try:
        listener_thread, publication_ready, publication_abandoned = (
            _start_runtime_components(
                rpc_mod,
                actual_host=actual_host,
                actual_port=actual_port,
                remote_enabled=composition["remote_enabled"],
                allowed_ips=composition["allowed_ips"],
                runtime=runtime,
            )
        )
        apply_deferred()
        runtime.bind_publication(
            listener_thread=listener_thread,
            runtime_manifest=runtime_manifest,
            actual_endpoint=actual_endpoint,
            runtime_id=rpc_mod._ADDON_RUNTIME_ID,
            server_started_at=server_started_at,
        )
        _publish_runtime(
            rpc_mod,
            runtime,
            listener_thread=listener_thread,
            runtime_manifest=runtime_manifest,
            actual_endpoint=actual_endpoint,
            server_started_at=server_started_at,
        )
        publication_ready.set()
    except BaseException as exc:
        combined_failure = _cleanup_failed_launch(
            rpc_mod,
            runtime,
            exc,
            listener_thread=listener_thread,
            publication_ready=publication_ready,
            publication_abandoned=publication_abandoned,
        )
        if not isinstance(exc, Exception):
            if combined_failure is not None:
                raise combined_failure from None
            raise
        raise _RpcStartRefusal(
            "RPC Server could not start its listener: "
            f"{rpc_mod._redact_rpc_diagnostic(exc)}"
        ) from exc
    return warning, actual_host, actual_port


def _publish_runtime(
    rpc_mod: Any,
    runtime: Any,
    *,
    listener_thread: Any,
    runtime_manifest: Any,
    actual_endpoint: dict[str, Any],
    server_started_at: str,
) -> None:
    if runtime.listener_thread is not listener_thread:
        raise RuntimeError("runtime publication thread identity changed")
    if runtime.runtime_manifest is not runtime_manifest:
        raise RuntimeError("runtime publication manifest identity changed")
    if runtime.actual_endpoint != actual_endpoint:
        raise RuntimeError("runtime publication endpoint changed")
    if runtime.server_started_at != server_started_at:
        raise RuntimeError("runtime publication timestamp changed")
    root = getattr(rpc_mod, "_root", rpc_mod)
    if root._addon_runtime is not None and not root._addon_runtime.disposed:
        raise RuntimeError("another runtime was published during startup")
    root._addon_runtime = runtime


def _unpublish_runtime(rpc_mod: Any, runtime: Any) -> None:
    """Make the exact runtime inactive while retaining its replay journal."""

    root = getattr(rpc_mod, "_root", rpc_mod)
    if root._addon_runtime is runtime and not getattr(runtime, "disposed", True):
        raise RuntimeError("an active runtime cannot be unpublished")
