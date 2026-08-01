"""Off-GUI baseline hashing for ``acquire_document_lock_v2``."""

import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from ._common import _rpc_mod


def hash_acquisition_baseline(self, phase):
    baseline = None
    path = phase["canonical_path"]
    if path:
        if not os.path.isfile(path):
            raise _rpc_mod()._import_document_lease().LeaseServiceError(
                "saved document path is missing or is not a regular file"
            )
        lease_mod = _rpc_mod()._import_document_lease()
        hash_platform = _rpc_mod().document_identity_service.platform

        def _hash_baseline():
            return lease_mod.capture_file_baseline(path, platform=hash_platform)

        hash_pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = hash_pool.submit(_hash_baseline)
            try:
                baseline = future.result(timeout=self.ACQUIRE_HASH_TIMEOUT_S)
            except FuturesTimeoutError as exc:
                future.cancel()
                # Do not wait for the orphaned hasher: waiting would
                # defeat the budget and leave ACQUIRING wedged longer.
                raise lease_mod.LeaseServiceError(
                    "acquisition baseline hashing exceeded "
                    f"{self.ACQUIRE_HASH_TIMEOUT_S}s budget"
                ) from exc
        finally:
            hash_pool.shutdown(wait=False, cancel_futures=True)
    phase["baseline"] = baseline
    return baseline


def rollback_after_hash_failure(self, phase, failure, request_id, acquire_timeout):
    def rollback_gui():
        credential = phase.get("credential")
        if credential is None:
            return _rpc_mod()._lease_service_error(failure, request_id=request_id)
        try:
            _rpc_mod().document_lease_service.abort_acquisition(credential)
            return _rpc_mod()._lease_service_error(failure, request_id=request_id)
        except Exception as rollback_exc:
            return _rpc_mod()._lease_service_error(rollback_exc, request_id=request_id)

    return self._dispatch_gui(rollback_gui, timeout=acquire_timeout)
