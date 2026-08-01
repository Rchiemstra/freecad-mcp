"""Authorization and hashing phases for LOCKED_ERROR handoff continuation."""

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from ._common import _rpc_mod, require_document_modified


def authorize_handoff_gui(
    self,
    *,
    cancelled,
    requested_selector,
    request_id,
    phase,
):
    try:
        if cancelled():
            return {
                "success": False,
                "error_code": "LOCKED_ERROR_HANDOFF_CANCELLED",
                "error": "LOCKED_ERROR handoff was cancelled before authorization",
                "request_id": request_id,
            }
        document, document_identity = _rpc_mod()._live_document_from_selector(
            requested_selector
        )
        if not require_document_modified(document):
            return {
                "success": False,
                "error_code": "DIRTY_ADOPTION_PRECONDITION_FAILED",
                "error": "the selected document has no unsaved changes to adopt",
                "request_id": request_id,
            }
        if not _rpc_mod()._authorize_locked_error_handoff_gui(
            document, document_identity
        ):
            return {
                "success": False,
                "error_code": "DIRTY_ADOPTION_PRECONDITION_FAILED",
                "error": "LOCKED_ERROR handoff was not authorized",
                "request_id": request_id,
            }
        if cancelled():
            return {
                "success": False,
                "error_code": "LOCKED_ERROR_HANDOFF_CANCELLED",
                "error": "LOCKED_ERROR handoff was cancelled after authorization",
                "request_id": request_id,
            }
        phase["locked_error_handoff"] = True
        phase["locked_error_handoff_authorized"] = True
        phase["document_identity"] = document_identity
        phase["document_name"] = document_identity.name
        phase["canonical_path"] = document_identity.canonical_path
        return {"success": True}
    except Exception as exc:
        return _rpc_mod()._lease_service_error(exc, request_id=request_id)


def hash_handoff_baseline(self, phase, lease, fail):
    """Hash off-GUI; return False when ``fail`` was invoked and continuation stops."""

    baseline = None
    path = phase.get("canonical_path")
    if path:
        if not os.path.isfile(path):
            fail(
                "LEASE_SERVICE_ERROR",
                "saved document path is missing or is not a regular file",
            )
            return False
        hash_platform = _rpc_mod().document_identity_service.platform

        def _hash_baseline():
            return lease.capture_file_baseline(path, platform=hash_platform)

        hash_pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = hash_pool.submit(_hash_baseline)
            try:
                baseline = future.result(timeout=self.ACQUIRE_HASH_TIMEOUT_S)
            except FuturesTimeoutError:
                future.cancel()
                fail(
                    "LEASE_SERVICE_ERROR",
                    "acquisition baseline hashing exceeded "
                    f"{self.ACQUIRE_HASH_TIMEOUT_S}s budget",
                )
                return False
        finally:
            hash_pool.shutdown(wait=False, cancel_futures=True)
    phase["baseline"] = baseline
    return True
