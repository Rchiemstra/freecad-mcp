"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from typing import Any

from ._common import _rpc_mod
from .release_gui import release_document_gui


def release_document_lock(
    self,
    doc_key: str = "",
    token: str = "",
    selector: dict[str, Any] | None = None,
    disposition: str = "saved",
) -> dict[str, Any]:
    try:
        dl = _rpc_mod()._import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false",
        }
    if _rpc_mod().document_lease_service is not None and selector is not None:
        captured_identity = dict(dl.get_request_identity())
        inflight = self._current_inflight()
        self._request_checkpoint("release_start")

        def task():
            try:
                return release_document_gui(
                    self,
                    selector=selector,
                    disposition=disposition,
                    captured_identity=captured_identity,
                    inflight=inflight,
                )
            except Exception as exc:
                return _rpc_mod()._lease_service_error(
                    exc, request_id=captured_identity.get("request_id")
                )

        return self._dispatch_gui(task, timeout=self.EXECUTE_TIMEOUT)
    result = dl.release_lease(doc_key, token)
    if result.get("success"):
        try:
            from lock_indicator import refresh_lock_indicator

            refresh_lock_indicator()
        except Exception:
            pass
    return result


def force_release_stale_lock(self, doc_key: str) -> dict[str, Any]:
    """Reject remote force release; recovery is a confirmed local GUI action.

    The method remains as a compatibility tombstone so an older client
    receives an explicit safe failure instead of an XML-RPC unknown-method
    fault.  In particular it must not become usable merely by switching a
    profile to observe/off mode.
    """
    del doc_key
    return {
        "success": False,
        "error_code": "LOCAL_RECOVERY_REQUIRED",
        "error": (
            "Stale or malformed lease recovery is available only from "
            "FreeCAD's local document-lock UI with explicit confirmation"
        ),
    }
