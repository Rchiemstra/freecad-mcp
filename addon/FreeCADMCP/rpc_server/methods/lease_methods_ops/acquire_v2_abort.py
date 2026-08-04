"""Best-effort rollback helpers for ``acquire_document_lock_v2``."""

from typing import Any

from ._common import logger
from .collaboration_dependencies import CollaborationCollaborators


def abort_phase_reservation(
    phase: dict[str, Any], collaborators: CollaborationCollaborators
) -> None:
    """Best-effort rollback of a mutation-free ACQUIRING reservation."""

    credential = phase.get("credential")
    if credential is None or collaborators.document_lease_service is None:
        return
    try:
        collaborators.document_lease_service.abort_acquisition(credential)
    except Exception:
        logger.exception(
            "Failed to abort unreturned acquisition reservation after timeout"
        )
    else:
        phase.pop("credential", None)
