"""Unscoped mutation handling for the application document observer."""

from __future__ import annotations

from typing import Any

from ._log import logger
from .document_helpers import document_dirty, document_from_subject
from .record_helpers import has_accepted_baseline, record_state
from .runtime_providers import get_runtime_service

_RECOVERY_STATES = frozenset({"USER_INTERVENED", "UNLOCKED_DIRTY"})


def _resolve_dirty(document: Any) -> bool:
    dirty = document_dirty(document)
    if dirty is None:
        return True
    return dirty


def _update_recovery_dirty_record(
    service: Any,
    identity: Any,
    dirty: bool,
) -> Any:
    updater = getattr(service, "update_local_dirty", None)
    if not callable(updater):
        return None
    try:
        return updater(identity.session_uuid, dirty=dirty)
    except Exception:
        logger.debug(
            "unable to refresh local recovery dirty state",
            exc_info=True,
        )
        return None


def _handle_save_start(
    observer: Any,
    *,
    service: Any,
    identity: Any,
    document: Any,
    current: Any,
    kind: str,
    detail: str,
    dirty: bool,
) -> Any:
    if has_accepted_baseline(current) and dirty is False:
        observer._pending_unscoped_gui_save[identity.session_uuid] = id(document)
        return current
    observer._pending_unscoped_gui_save.pop(identity.session_uuid, None)
    return observer._takeover_unscoped_change(
        service,
        identity,
        document,
        kind=kind,
        detail=detail,
        dirty=dirty,
    )


def _handle_save_finish_or_close(
    observer: Any,
    *,
    service: Any,
    identity: Any,
    document: Any,
    kind: str,
    detail: str,
    dirty: bool,
    is_save_finish: bool,
) -> Any:
    observer._pending_unscoped_gui_save.pop(identity.session_uuid, None)
    trigger = (
        "gui_save_finish" if is_save_finish else "gui_save_close_without_finish"
    )
    return observer._preserve_or_fence_after_gui_save(
        service,
        identity,
        document,
        kind=kind,
        detail=detail,
        dirty=dirty,
        trigger=trigger,
    )


def _maybe_refresh_recovery_identity(
    service: Any,
    identity: Any,
    document: Any,
    record: Any,
    *,
    refresh_saved_identity: bool,
) -> Any:
    if not refresh_saved_identity:
        return record
    recovery_state = record_state(record)
    if recovery_state not in _RECOVERY_STATES:
        return record
    refresher = getattr(service, "refresh_local_recovery_document_identity", None)
    if not callable(refresher):
        return record
    try:
        return refresher(identity.session_uuid, document=document)
    except Exception:
        logger.warning(
            "unable to refresh GUI-saved document identity",
            exc_info=True,
        )
        return record


def _process_leased_change(
    observer: Any,
    *,
    service: Any,
    identity: Any,
    document: Any,
    current: Any,
    kind: str,
    detail: str,
    force: bool,
    refresh_saved_identity: bool,
) -> Any | None:
    if not force and observer._is_agent_attributed(document, identity):
        return None
    dirty = _resolve_dirty(document)
    recovery_state = record_state(current)
    is_recovery_state = recovery_state in _RECOVERY_STATES
    is_save_start = kind == "save" and not refresh_saved_identity
    is_save_finish = kind == "save" and refresh_saved_identity
    pending_close_save = (
        kind == "document close"
        and refresh_saved_identity
        and identity.session_uuid in observer._pending_unscoped_gui_save
    )
    record = current
    if is_recovery_state:
        updated = _update_recovery_dirty_record(service, identity, dirty)
        if updated is not None:
            record = updated
    elif is_save_start:
        record = _handle_save_start(
            observer,
            service=service,
            identity=identity,
            document=document,
            current=current,
            kind=kind,
            detail=detail,
            dirty=dirty,
        )
    elif is_save_finish or pending_close_save:
        record = _handle_save_finish_or_close(
            observer,
            service=service,
            identity=identity,
            document=document,
            kind=kind,
            detail=detail,
            dirty=dirty,
            is_save_finish=is_save_finish,
        )
    else:
        record = observer._takeover_unscoped_change(
            service,
            identity,
            document,
            kind=kind,
            detail=detail,
            dirty=dirty,
        )
    return _maybe_refresh_recovery_identity(
        service,
        identity,
        document,
        record,
        refresh_saved_identity=refresh_saved_identity,
    )


def handle_unscoped_change(
    observer: Any,
    document: Any,
    kind: str,
    *,
    detail: str = "",
    force: bool = False,
    refresh_saved_identity: bool = False,
) -> Any | None:
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
            try:
                current = service.get(identity.session_uuid)
            except Exception:
                logger.debug(
                    "unable to inspect selected document lease", exc_info=True
                )
                return None
            if current is None:
                if refresh_saved_identity:
                    observer._refresh_unleased_saved_identity(
                        service,
                        identity,
                        document,
                    )
                return None
            return _process_leased_change(
                observer,
                service=service,
                identity=identity,
                document=document,
                current=current,
                kind=kind,
                detail=detail,
                force=force,
                refresh_saved_identity=refresh_saved_identity,
            )
    except Exception:
        logger.warning("unable to fence unscoped FreeCAD change", exc_info=True)
        return None
