"""XML-RPC listener start orchestration."""

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
        rpc_mod.os.path.dirname(__file__),
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
    rpc_mod.rpc_server_started_at = (
        datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    return str(actual_host), int(actual_port)


def _launch_listener_thread(
    rpc_mod: Any,
    *,
    actual_host: str,
    actual_port: int,
    remote_enabled: bool,
    allowed_ips: str,
    settings: dict[str, Any],
) -> None:
    rpc_mod.rpc_server_instance.register_instance(
        rpc_mod.FreeCADRPC(
            allow_execute_code=(
                not remote_enabled
                or bool(settings.get("allow_remote_execute_code", False))
            )
        )
    )

    def server_loop():
        logger.info("RPC Server started at %s:%s", actual_host, actual_port)
        if remote_enabled:
            logger.info("Remote connections enabled. Allowed IPs: %s", allowed_ips)
        rpc_mod.rpc_server_instance.serve_forever()

    rpc_mod.rpc_server_thread = rpc_mod.threading.Thread(target=server_loop, daemon=True)
    rpc_mod.rpc_server_thread.start()


def start_rpc_server(port=None):
    from . import rpc_server as rpc_mod
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
    rpc_mod.gui_dispatcher = rpc_mod.GuiDispatcher(parent)

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
    rpc_mod.worker_manager = _build_worker_manager(rpc_mod, settings)

    lease_mode = str(settings.get("document_lease_mode", "off"))
    try:
        rpc_mod.initialize_document_lease_runtime(settings)
    except Exception as exc:
        abort_rpc_start(rpc_mod)
        return f"RPC Server refused document lease runtime configuration: {exc}"

    bind_result = _bind_listener(rpc_mod, settings, port, allowed_ips)
    if isinstance(bind_result, str):
        return bind_result
    actual_host, actual_port = bind_result

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

    rpc_v2_initialization_warning = initialize_rpc_v2_session(
        rpc_mod,
        profile_id=profile_id,
        auth_secret_file=auth_secret_file,
        lease_mode=lease_mode,
        actual_host=actual_host,
        actual_port=actual_port,
    )
    if rpc_v2_initialization_warning.startswith("RPC Server could not"):
        return rpc_v2_initialization_warning

    _launch_listener_thread(
        rpc_mod,
        actual_host=actual_host,
        actual_port=actual_port,
        remote_enabled=remote_enabled,
        allowed_ips=allowed_ips,
        settings=settings,
    )

    msg = f"RPC Server started at {actual_host}:{actual_port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    msg += rpc_v2_initialization_warning
    return msg
