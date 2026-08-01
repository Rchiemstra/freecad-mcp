"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

from typing import Any

from ._common import _rpc_mod


def execute_code_worker(
    self, code: str, options: dict[str, Any]
) -> dict[str, Any]:
    manager = _rpc_mod().worker_manager
    if manager is None:
        return {
            "success": False,
            "is_error": True,
            "error_code": "worker_unavailable",
            "error": "FreeCADCmd worker manager is not initialized",
        }
    try:
        workspace = manager.create_workspace()
    except Exception as exc:
        return {
            "success": False,
            "is_error": True,
            "error_code": "worker_unavailable",
            "error": str(exc),
        }

    snapshot = None
    mutation_context = _rpc_mod()._snapshot_mutation_context_for_request()
    with _rpc_mod().snapshot_coordinator:
        for attempt in range(2):
            def create_snapshot_task():
                return _rpc_mod().create_primary_snapshot_gui(
                    options.get("document"),
                    str(workspace),
                    link_policy=str(options.get("link_policy") or "strict"),
                    mutation_generations=mutation_context["generations"],
                    mutation_request_id=mutation_context["request_id"],
                    mutation_document_keys=mutation_context["document_keys"],
                )

            snapshot = self._dispatch_snapshot_gui(create_snapshot_task)
            if not isinstance(snapshot, dict):
                break
            if (
                snapshot.get("error_code") != "snapshot_state_changed"
                or attempt == 1
            ):
                break
    if not isinstance(snapshot, dict) or not snapshot.get("ok"):
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)
        if isinstance(snapshot, dict):
            return {
                "success": False,
                "is_error": True,
                "error_code": snapshot.get("error_code", "snapshot_failed"),
                "error": snapshot.get("error", "Snapshot creation failed"),
            }
        return {
            "success": False,
            "is_error": True,
            "error_code": "snapshot_failed",
            "error": str(snapshot),
        }
    return manager.execute(code, options, snapshot, workspace)
