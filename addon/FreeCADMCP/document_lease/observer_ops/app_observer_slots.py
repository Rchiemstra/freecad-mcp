"""FreeCAD App::DocumentObserverPython slot callbacks."""

from __future__ import annotations

from typing import Any

from ._log import logger
from .document_helpers import document_dirty, document_from_subject
from .live_document_recovery import register_live_document_recovery
from .runtime_providers import get_runtime_service, is_internal_snapshot_save


def slot_created_document(observer: Any, document: Any) -> Any | None:
    service = get_runtime_service(observer._service_provider)
    if service is None:
        return None
    if not str(getattr(document, "FileName", "") or "").strip():
        return None
    try:
        identity, imported, _failure = register_live_document_recovery(
            service, document
        )
        if imported is not None:
            observer._notify(
                kind="foreign recovery import",
                identity=identity,
                reason="Imported adjacent v2 recovery authority",
                dirty=document_dirty(document),
                record=imported,
            )
        return imported
    except Exception:
        logger.warning(
            "unable to import adjacent document recovery sidecar",
            exc_info=True,
        )
        return None


def slot_before_change_object(observer: Any, obj: Any, prop: Any) -> Any | None:
    return observer._handle(obj, "object property change", detail=str(prop))


def slot_changed_object(observer: Any, obj: Any, prop: Any) -> Any | None:
    return observer._handle(obj, "object property change", detail=str(prop))


def slot_created_object(observer: Any, obj: Any) -> Any | None:
    return observer._handle(obj, "object creation")


def slot_deleted_object(observer: Any, obj: Any) -> Any | None:
    return observer._handle(obj, "object deletion")


def slot_append_dynamic_property(
    observer: Any, container: Any, prop: Any
) -> Any | None:
    return observer._handle(
        container,
        "dynamic property addition",
        detail=str(prop),
    )


def slot_remove_dynamic_property(
    observer: Any, container: Any, prop: Any
) -> Any | None:
    return observer._handle(
        container,
        "dynamic property removal",
        detail=str(prop),
    )


def slot_change_property_editor(
    observer: Any, container: Any, prop: Any
) -> Any | None:
    return observer._handle(
        container,
        "property editor change",
        detail=str(prop),
    )


def slot_before_adding_dynamic_extension(
    observer: Any, container: Any, extension: Any
) -> Any | None:
    return observer._handle(
        container,
        "dynamic extension addition",
        detail=str(extension),
    )


def slot_added_dynamic_extension(
    observer: Any, container: Any, extension: Any
) -> Any | None:
    return observer._handle(
        container,
        "dynamic extension addition",
        detail=str(extension),
    )


def slot_before_change_document(
    observer: Any, document: Any, prop: Any
) -> Any | None:
    return observer._handle(document, "document property change", detail=str(prop))


def slot_changed_document(observer: Any, document: Any, prop: Any) -> Any | None:
    return observer._handle(document, "document property change", detail=str(prop))


def slot_relabel_document(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "document relabel")


def slot_undo_document(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "undo")


def slot_redo_document(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "redo")


def slot_undo(observer: Any) -> Any | None:
    return observer._handle_selected("undo")


def slot_redo(observer: Any) -> Any | None:
    return observer._handle_selected("redo")


def slot_before_recompute_document(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "recompute")


def slot_recomputed_document(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "recompute")


def slot_recomputed_object(observer: Any, obj: Any) -> Any | None:
    return observer._handle(obj, "object recompute")


def slot_open_transaction(observer: Any, document: Any, name: Any) -> Any | None:
    return observer._handle(document, "transaction open", detail=str(name))


def slot_commit_transaction(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "transaction commit")


def slot_abort_transaction(observer: Any, document: Any) -> Any | None:
    return observer._handle(document, "transaction abort")


def slot_before_close_transaction(observer: Any, abort: Any) -> Any | None:
    action = "transaction abort" if abort else "transaction commit"
    return observer._handle_selected(action)


def slot_close_transaction(observer: Any, abort: Any) -> Any | None:
    action = "transaction abort" if abort else "transaction commit"
    return observer._handle_selected(action)


def slot_start_save_document(
    observer: Any, document: Any, filename: Any
) -> Any | None:
    if is_internal_snapshot_save(document, filename):
        return None
    return observer._handle(document, "save", detail=str(filename or ""))


def slot_finish_save_document(
    observer: Any, document: Any, filename: Any
) -> Any | None:
    if is_internal_snapshot_save(document, filename):
        return None
    record = observer._handle(
        document,
        "save",
        detail=str(filename or ""),
        refresh_saved_identity=True,
    )
    if document_dirty(document_from_subject(document)) is not False:
        try:
            observer._notification_queue(
                lambda: observer._refresh_finished_save(document)
            )
        except Exception:
            logger.warning(
                "completed-save refresh queue failed",
                exc_info=True,
            )
    return record


def slot_deleted_document(observer: Any, document: Any) -> Any | None:
    document = document_from_subject(document)
    record = observer._handle(
        document,
        "document close",
        refresh_saved_identity=True,
    )
    if document is None:
        return record
    try:
        service = get_runtime_service(observer._service_provider)
        if service is None:
            return record
        identity = observer._identity_for_document(service, document)
        closer = getattr(service, "handle_document_closed", None)
        if identity is None or not callable(closer):
            return record
        closed = closer(identity.session_uuid, document=document)
        return record if record is not None else closed
    except Exception:
        logger.warning(
            "unable to retain or unregister closed document identity",
            exc_info=True,
        )
        return record
