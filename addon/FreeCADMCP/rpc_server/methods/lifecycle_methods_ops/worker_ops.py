import threadingimport typingfrom ...parts_library import get_parts_list as library_get_parts_listfrom ...server_shutdown import stop_rpc_serverfrom ._common import _rpc_mod"""Worker manager and shutdown RPC methods."""


def get_worker_status(self) -> dict[str, typing.Any]:
    manager = _rpc_mod().worker_manager
    if manager is None:
        return {
            "available": False,
            "busy": False,
            "queue_depth": 0,
            "last_error": "Worker manager is not initialized",
        }
    return manager.status()


def cancel_worker_job(self, job_id: str) -> dict[str, typing.Any]:
    manager = _rpc_mod().worker_manager
    if manager is None:
        return {
            "success": False,
            "error_code": "worker_unavailable",
            "error": "Worker manager is not initialized",
        }
    return manager.cancel(job_id)


def shutdown_rpc_server(self) -> dict[str, typing.Any]:
    """Admit shutdown through the reserved control lane and respond first."""
    if _rpc_mod().shutdown_requested.is_set():
        return {"success": True, "state": "already_stopping"}
    _rpc_mod().shutdown_requested.set()
    timer = threading.Timer(0.05, stop_rpc_server)
    timer.name = "FreeCADMCP-RPC-Shutdown"
    timer.daemon = True
    timer.start()
    return {"success": True, "state": "stopping"}


def get_parts_list(self):
    return library_get_parts_list()
