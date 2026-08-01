"""Deferred save refresh after FreeCAD clears ``Modified``."""

from __future__ import annotations

from typing import Any

from ._log import logger
from .document_helpers import document_dirty, document_from_subject
from .record_helpers import record_state
from .runtime_providers import get_runtime_service

_RECOVERY_STATES = frozenset({"USER_INTERVENED", "UNLOCKED_DIRTY"})
_LOCKED_STATES = frozenset(
    {
        "LOCKED_IDLE",
        "LOCKED_EDITING",
        "LOCKED_RECOMPUTING",
        "LOCKED_SAVING",
        "LOCKED_ERROR",
        "ACQUIRING",
        "STALE",
    }
)


def _update_recovery_dirty(
    service: Any,
    identity: Any,
    dirty: bool,
) -> Any:
    updater = getattr(service, "update_local_dirty", None)
    if not callable(updater):
        return None
    return updater(identity.session_uuid, dirty=dirty)


def _try_deferred_baseline_refresh(
    service: Any,
    identity: Any,
    document: Any,
) -> Any | None:
    inplace_refresher = getattr(
        service,
        "try_baseline_preserving_document_identity_refresh",
        None,
    )
    if not callable(inplace_refresher):
        return None
    try:
        return inplace_refresher(
            identity.session_uuid,
            document=document,
            trigger="gui_save_finish_deferred",
        )
    except Exception:
        logger.debug(
            "deferred baseline-preserving refresh failed",
            exc_info=True,
        )
        return None


def _refresh_recovery_identity(
    service: Any,
    identity: Any,
    document: Any,
) -> Any | None:
    refresher = getattr(service, "refresh_local_recovery_document_identity", None)
    if not callable(refresher):
        return None
    return refresher(identity.session_uuid, document=document)


def _apply_deferred_dirty_refresh(
    service: Any,
    identity: Any,
    document: Any,
    *,
    record: Any,
    recovery_state: str,
    dirty: bool,
) -> Any:
    is_recovery_state = recovery_state in _RECOVERY_STATES
    if is_recovery_state:
        updated = _update_recovery_dirty(service, identity, dirty)
        if updated is not None:
            return updated
        return record
    if recovery_state in _LOCKED_STATES:
        refreshed = _try_deferred_baseline_refresh(service, identity, document)
        if refreshed is not None:
            return refreshed
    return record


def refresh_finished_save(observer: Any, document: Any) -> Any | None:
    """Refresh recovery state after FreeCAD finishes clearing ``Modified``."""

    document = document_from_subject(document)
    if document is None:
        return None
    try:
        service = get_runtime_service(observer._service_provider)
        if service is None:
            return None
        with observer._event_lock:
            identity = observer._identity_for_document(service, document)
            if identity is None:
                return None
            current = service.get(identity.session_uuid)
            if current is None:
                observer._refresh_unleased_saved_identity(
                    service,
                    identity,
                    document,
                )
                return None
            recovery_state = record_state(current)
            is_recovery_state = recovery_state in _RECOVERY_STATES
            dirty = document_dirty(document)
            record = current
            if dirty is not None:
                record = _apply_deferred_dirty_refresh(
                    service,
                    identity,
                    document,
                    record=record,
                    recovery_state=recovery_state,
                    dirty=dirty,
                )
            if is_recovery_state:
                refreshed = _refresh_recovery_identity(service, identity, document)
                if refreshed is not None:
                    record = refreshed
            return record
    except Exception:
        logger.warning(
            "unable to refresh completed FreeCAD save",
            exc_info=True,
        )
        return None
