"""Best-effort rollback helpers for ``acquire_document_lock_v2``."""

from typing import Any

from ._common import _rpc_mod, logger


def abort_phase_reservation(phase: dict[str, Any]) -> None:
    """Best-effort rollback of a mutation-free ACQUIRING reservation."""

    credential = phase.get("credential")
    if credential is None or _rpc_mod().document_lease_service is None:
        return
    try:
        _rpc_mod().document_lease_service.abort_acquisition(credential)
    except Exception:
        logger.exception(
            "Failed to abort unreturned acquisition reservation after timeout"
        )
    else:
        phase.pop("credential", None)
