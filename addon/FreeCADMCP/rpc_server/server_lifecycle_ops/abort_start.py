"""Abort an in-progress RPC listener start and reset module state."""

from __future__ import annotations

from typing import Any


def abort_rpc_start(rpc_mod: Any, *, close_listener: bool = False) -> None:
    if close_listener and rpc_mod.rpc_server_instance is not None:
        rpc_mod.rpc_server_instance.server_close()
    rpc_mod.rpc_server_instance = None
    rpc_mod.rpc_server_thread = None
    if rpc_mod.gui_dispatcher is not None:
        rpc_mod.gui_dispatcher.deleteLater()
    rpc_mod.gui_dispatcher = None
    rpc_mod.worker_manager = None
    rpc_mod.rpc_server_runtime_id = ""
    rpc_mod.rpc_server_started_at = ""
    rpc_mod.rpc_server_actual_endpoint = None
    rpc_mod.rpc_session_manager = None
    rpc_mod.rpc_runtime_manifest = None
