"""JSON-RPC listener start orchestration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import FreeCAD

logger = logging.getLogger("FreeCADMCP.rpc_server")


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


def _bind_listener(
    rpc_mod: Any,
    settings: dict[str, Any],
    port: int,
    allowed_ips: str,
) -> tuple[str, int] | str:
    from .server_lifecycle_ops.abort_start import abort_rpc_start

    try:
        host = rpc_mod.resolve_rpc_bind_host(settings)
    except rpc_mod.SettingsPolicyError as exc:
        abort_rpc_start(rpc_mod)
        return f"RPC Server refused unsafe configuration: {exc}"
    rpc_mod.rpc_server_instance = rpc_mod.FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    actual_host, actual_port = rpc_mod.rpc_server_instance.server_address[:2]
    rpc_mod.rpc_server_actual_endpoint = {"host": actual_host, "port": int(actual_port)}
    rpc_mod.rpc_server_runtime_id = rpc_mod._ADDON_RUNTIME_ID
    rpc_mod.rpc_server_started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return str(actual_host), int(actual_port)


def _launch_listener_thread(
    rpc_mod: Any,
    *,
    actual_host: str,
    actual_port: int,
    remote_enabled: bool,
    allowed_ips: str,
    runtime: Any,
) -> None:
    if runtime is None:
        raise RuntimeError("RPC runtime was not composed before listener launch")
    # The composition root has already registered the bridge exactly once.
    # Launch intentionally avoids SimpleXMLRPCServer's private `instance` detail,
    # so a listener substitute needs only the documented registration method and
    # cannot receive a duplicate registration as the serving thread is launched.
    # Keep all adapter-specific graph wiring in `_build_addon_runtime`.
    start_worker = getattr(runtime.worker_manager, "_start", None)
    if callable(start_worker):
        start_worker()

    def server_loop():
        logger.info("RPC Server started at %s:%s", actual_host, actual_port)
        if remote_enabled:
            logger.info("Remote connections enabled. Allowed IPs: %s", allowed_ips)
        runtime.listener.serve_forever()

    rpc_mod.rpc_server_thread = rpc_mod.threading.Thread(target=server_loop, daemon=True)
    rpc_mod.rpc_server_thread.start()


def start_rpc_server(port=None):
    from . import rpc_server as rpc_mod
    try:
        from ..runtime import _build_addon_runtime
    except ImportError:  # pragma: no cover - flat addon import path
        from runtime import _build_addon_runtime
    from .server_lifecycle_ops.abort_start import abort_rpc_start
    from .server_lifecycle_ops.start_gates import (
        refuse_enforce_without_profile,
        refuse_off_mode_with_active_records,
        register_live_documents,
    )
    from .server_lifecycle_ops.v2_session import initialize_rpc_v2_session

    if rpc_mod.rpc_server_instance:
        return "RPC Server already running."
    rpc_mod.shutdown_requested.clear()

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

    lease_mode = str(settings.get("document_lease_mode", "off"))
    try:
        rpc_mod.initialize_document_lease_runtime(settings)
    except Exception as exc:
        abort_rpc_start(rpc_mod)
        return f"RPC Server refused document lease runtime configuration: {exc}"

    profile_id = str(
        settings.get("profile_instance_id") or settings.get("instance_id") or ""
    )
    auth_secret_file = str(settings.get("auth_secret_file") or "")

    enforce_error = refuse_enforce_without_profile(
        rpc_mod,
        lease_mode=lease_mode,
        profile_id=profile_id,
        auth_secret_file=auth_secret_file,
    )
    if enforce_error is not None:
        return enforce_error

    register_live_documents(rpc_mod, lease_mode)
    off_mode_error = refuse_off_mode_with_active_records(rpc_mod, lease_mode)
    if off_mode_error is not None:
        return off_mode_error

    try:
        rpc_v2_initialization_warning, actual_host, actual_port = (
            _construct_and_launch_transitional_runtime(
                _build_addon_runtime,
                rpc_mod,
                parent=parent,
                settings=settings,
                port=port,
                allowed_ips=allowed_ips,
                remote_enabled=remote_enabled,
                lease_mode=lease_mode,
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


_PREDICATE_BINDING_NAME = "set_owner_lease_predicate"


class _DeferredReplayBinding:
    def __init__(self, source: Any) -> None:
        self._source = source
        self._predicate = None

    def __getattr__(self, name: str) -> Any:
        if name == _PREDICATE_BINDING_NAME:
            return self._capture
        return getattr(self._source, name)

    def _capture(self, predicate) -> None:
        if not callable(predicate):
            raise TypeError("replay predicate must be callable")
        self._predicate = predicate

    def apply(self) -> None:
        if self._predicate is not None:
            getattr(self._source, _PREDICATE_BINDING_NAME)(self._predicate)


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
                "rpc_request_replay_cache": _DeferredReplayBinding(replay_cache),
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
        binding = self.staged("rpc_request_replay_cache")
        binding.apply()


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


def _compose_transitional_runtime(
    builder,
    rpc_mod: Any,
    *,
    parent: Any,
    settings: dict[str, Any],
    port: int,
    allowed_ips: str,
    remote_enabled: bool,
    lease_mode: str,
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
        _handoff_continuations,
        _acquisition_claims,
    ):
        collaboration_collaborators = rpc_mod._build_collaboration_collaborators()
        bridge = rpc_mod.FreeCADRPC(
            allow_execute_code=(
                not remote_enabled
                or bool(settings.get("allow_remote_execute_code", False))
            ),
            collaboration_collaborators=collaboration_collaborators,
            execution_collaborators=rpc_mod._build_execution_collaborators(
                compatibility_api=collaboration_collaborators.compatibility_api,
                gui_dispatcher_value=_dispatcher,
                worker_manager_value=_worker_manager,
                request_replay_cache=_request_replay_cache,
                inflight_request_registry=_inflight_requests,
                handoff_continuation_store=_handoff_continuations,
                acquisition_claim_store=_acquisition_claims,
                session_manager_value=None,
                runtime_manifest_value=None,
                actual_endpoint_value=None,
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
            lease_mode=lease_mode,
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
        authentication_required=(lease_mode == "enforce"),
        request_replay_cache=rpc_mod.rpc_request_replay_cache,
        inflight_requests=rpc_mod.rpc_inflight_request_registry,
        handoff_continuations=rpc_mod.rpc_handoff_continuation_store,
        acquisition_claims=rpc_mod.rpc_acquisition_claim_store,
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


def _construct_and_launch_transitional_runtime(
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
            _compose_transitional_runtime(
                builder,
                rpc_mod,
                **composition,
            )
        )
    except _RpcStartRefusal:
        raise
    except Exception as exc:
        logger.error("Could not construct RPC runtime: %s", exc)
        raise _RpcStartRefusal(
            "RPC Server could not construct its runtime: "
            f"{rpc_mod._redact_rpc_diagnostic(exc)}"
        ) from exc

    try:
        _publish_transitional_runtime(
            rpc_mod,
            runtime,
            runtime_manifest=runtime_manifest,
            apply_deferred=apply_deferred,
            actual_host=actual_host,
            actual_port=actual_port,
            actual_endpoint=actual_endpoint,
            server_started_at=server_started_at,
        )
        _launch_listener_thread(
            rpc_mod,
            actual_host=actual_host,
            actual_port=actual_port,
            remote_enabled=composition["remote_enabled"],
            allowed_ips=composition["allowed_ips"],
            runtime=runtime,
        )
    except BaseException as exc:
        cleanup_failure = None
        try:
            runtime.dispose()
        except BaseException as cleanup_exc:
            cleanup_failure = cleanup_exc
            logger.exception("Could not fully dispose failed RPC runtime")
        finally:
            _unpublish_transitional_runtime(rpc_mod, runtime)
        if not isinstance(exc, Exception):
            if cleanup_failure is not None:
                raise BaseExceptionGroup(
                    "RPC runtime launch and cleanup failed",
                    (exc, cleanup_failure),
                ) from None
            raise
        raise _RpcStartRefusal(
            "RPC Server could not start its listener: "
            f"{rpc_mod._redact_rpc_diagnostic(exc)}"
        ) from exc
    rpc_mod._addon_runtime = runtime
    return warning, actual_host, actual_port


def _publish_transitional_runtime(
    rpc_mod: Any,
    runtime: Any,
    *,
    runtime_manifest: Any,
    apply_deferred,
    actual_host: str,
    actual_port: int,
    actual_endpoint: dict[str, Any],
    server_started_at: str,
) -> None:
    rpc_mod.rpc_server_instance = runtime.listener
    rpc_mod.gui_dispatcher = runtime.dispatcher
    rpc_mod.worker_manager = runtime.worker_manager
    rpc_mod.rpc_session_manager = runtime.session_manager
    rpc_mod.rpc_request_replay_cache = runtime.request_replay_cache
    rpc_mod.rpc_inflight_request_registry = runtime.inflight_requests
    rpc_mod.rpc_handoff_continuation_store = runtime.handoff_continuations
    rpc_mod.rpc_acquisition_claim_store = runtime.acquisition_claims
    rpc_mod.rpc_runtime_manifest = runtime_manifest
    apply_deferred()
    rpc_mod.rpc_server_actual_endpoint = actual_endpoint
    rpc_mod.rpc_server_runtime_id = rpc_mod._ADDON_RUNTIME_ID
    rpc_mod.rpc_server_started_at = server_started_at


def _unpublish_transitional_runtime(rpc_mod: Any, runtime: Any) -> None:
    """Remove only the aliases published for a graph that failed to launch."""

    aliases = (
        ("rpc_server_instance", runtime.listener),
        ("gui_dispatcher", runtime.dispatcher),
        ("worker_manager", runtime.worker_manager),
        ("rpc_session_manager", runtime.session_manager),
    )
    for name, component in aliases:
        if getattr(rpc_mod, name, None) is component:
            setattr(rpc_mod, name, None)
    rpc_mod.rpc_server_thread = None
    rpc_mod.rpc_server_runtime_id = ""
    rpc_mod.rpc_server_started_at = ""
    rpc_mod.rpc_server_actual_endpoint = None
    rpc_mod.rpc_runtime_manifest = None
