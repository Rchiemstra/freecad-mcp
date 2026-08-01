"""Application document observer for unscoped modelling changes."""

from __future__ import annotations

import threading
from typing import Any

from .. import observer as observer_mod
from . import app_observer_slots as slots
from ._log import logger
from .document_helpers import document_keys
from .events import (
    AgentMutationChecker,
    DocumentProvider,
    LeaseObserverEvent,
    NotificationCallback,
    NotificationQueue,
    ServiceProvider,
)
from .handle_unscoped_change import handle_unscoped_change
from .record_helpers import record_generation, record_state
from .refresh_finished_save import refresh_finished_save


class LeaseObserver:
    """Application document observer for unscoped modelling changes."""

    def __init__(
        self,
        *,
        service_provider: ServiceProvider | None = None,
        agent_mutation_checker: AgentMutationChecker | None = None,
        selected_document_provider: DocumentProvider | None = None,
        notification_callback: NotificationCallback | None = None,
        notification_queue: NotificationQueue | None = None,
    ) -> None:
        self._service_provider = service_provider or observer_mod._default_service_provider
        self._agent_mutation_checker = (
            agent_mutation_checker or observer_mod._default_agent_mutation_checker
        )
        self._selected_document_provider = (
            selected_document_provider
            or observer_mod._default_selected_document_provider
        )
        self._notification_callback = notification_callback
        self._notification_queue = notification_queue or observer_mod._qt_or_direct_queue
        self._event_lock = threading.RLock()
        self._pending_unscoped_gui_save: dict[str, int] = {}

    def _is_agent_attributed(self, document: Any, identity: Any | None = None) -> bool:
        for key in document_keys(document, identity):
            try:
                if self._agent_mutation_checker(key):
                    return True
            except Exception:
                logger.debug("mutation checker failed", exc_info=True)
        return False

    @staticmethod
    def _identity_for_document(service: Any, document: Any) -> Any | None:
        identity_service = getattr(service, "identity_service", None)
        if identity_service is None:
            return None
        name = str(getattr(document, "Name", "") or "").strip()
        filename = str(getattr(document, "FileName", "") or "").strip()
        selectors: list[dict[str, str]] = []
        if name:
            selectors.append({"document_name": name})
        if filename:
            selectors.append({"canonical_path": filename})
        for selector in selectors:
            try:
                identity = identity_service.resolve(selector)
            except Exception:
                continue
            inspector = getattr(
                identity_service,
                "inspect_registered_document",
                None,
            )
            if callable(inspector):
                try:
                    inspector(identity.session_uuid, document)
                except Exception:
                    continue
            return identity
        return None

    def _notify(
        self,
        *,
        kind: str,
        identity: Any,
        reason: str,
        dirty: bool | None,
        record: Any,
    ) -> None:
        callback = self._notification_callback
        if callback is None:
            return
        event = LeaseObserverEvent(
            kind=kind,
            document_name=str(getattr(identity, "name", "") or ""),
            document_session_uuid=str(getattr(identity, "session_uuid", "") or ""),
            canonical_path=getattr(identity, "canonical_path", None),
            reason=reason,
            dirty=dirty,
            state=record_state(record),
            generation=record_generation(record),
        )

        def deliver() -> None:
            try:
                callback(event)
            except Exception:
                logger.warning("lease observer notification failed", exc_info=True)

        try:
            self._notification_queue(deliver)
        except Exception:
            logger.warning("lease observer notification queue failed", exc_info=True)

    @staticmethod
    def _refresh_unleased_saved_identity(
        service: Any,
        identity: Any,
        document: Any,
    ) -> None:
        identities = getattr(service, "identity_service", None)
        refresher = getattr(identities, "refresh_saved_document", None)
        if not callable(refresher):
            return
        try:
            refreshed = refresher(document)
            if refreshed.session_uuid != identity.session_uuid:
                raise RuntimeError("saved document identity changed its live session")
        except Exception:
            logger.warning(
                "unable to refresh unleased GUI-saved document identity",
                exc_info=True,
            )

    def _takeover_unscoped_change(
        self,
        service: Any,
        identity: Any,
        document: Any,
        *,
        kind: str,
        detail: str,
        dirty: bool | None,
    ) -> Any:
        reason = f"Unscoped FreeCAD {kind} detected"
        if detail:
            clean_detail = " ".join(str(detail).split())[:512]
            if clean_detail:
                reason += f": {clean_detail}"
        reason = reason[:2048]
        record = service.takeover(
            identity.session_uuid,
            dirty=dirty,
            reason=reason,
        )
        try:
            from document_lease import core_authority

            core_authority.bump_takeover(document)
        except Exception:
            logger.debug("core mutation takeover sync failed", exc_info=True)
        self._notify(
            kind=kind,
            identity=identity,
            reason=reason,
            dirty=dirty,
            record=record,
        )
        return record

    def _preserve_or_fence_after_gui_save(
        self,
        service: Any,
        identity: Any,
        document: Any,
        *,
        kind: str,
        detail: str,
        dirty: bool | None,
        trigger: str,
    ) -> Any:
        inplace_refresher = getattr(
            service,
            "try_baseline_preserving_document_identity_refresh",
            None,
        )
        refreshed = None
        if callable(inplace_refresher):
            try:
                refreshed = inplace_refresher(
                    identity.session_uuid,
                    document=document,
                    trigger=trigger,
                )
            except Exception:
                logger.debug(
                    "baseline-preserving save refresh failed",
                    exc_info=True,
                )
        if refreshed is not None:
            return refreshed
        return self._takeover_unscoped_change(
            service,
            identity,
            document,
            kind=kind,
            detail=detail,
            dirty=dirty,
        )

    def _handle(
        self,
        document: Any,
        kind: str,
        *,
        detail: str = "",
        force: bool = False,
        refresh_saved_identity: bool = False,
    ) -> Any | None:
        return handle_unscoped_change(
            self,
            document,
            kind,
            detail=detail,
            force=force,
            refresh_saved_identity=refresh_saved_identity,
        )

    def _handle_selected(self, kind: str, *, detail: str = "") -> Any | None:
        try:
            document = self._selected_document_provider()
        except Exception:
            logger.debug("selected document provider failed", exc_info=True)
            return None
        return self._handle(document, kind, detail=detail)

    def _refresh_finished_save(self, document: Any) -> Any | None:
        return refresh_finished_save(self, document)

    def take_over_selected_document(
        self, *, reason: str = "Local user selected Take Over"
    ) -> Any | None:
        try:
            document = self._selected_document_provider()
        except Exception:
            logger.debug("selected document provider failed", exc_info=True)
            return None
        return self._handle(document, "manual takeover", detail=reason, force=True)

    slotCreatedDocument = slots.slot_created_document
    slotBeforeChangeObject = slots.slot_before_change_object
    slotChangedObject = slots.slot_changed_object
    slotCreatedObject = slots.slot_created_object
    slotDeletedObject = slots.slot_deleted_object
    slotAppendDynamicProperty = slots.slot_append_dynamic_property
    slotRemoveDynamicProperty = slots.slot_remove_dynamic_property
    slotChangePropertyEditor = slots.slot_change_property_editor
    slotBeforeAddingDynamicExtension = slots.slot_before_adding_dynamic_extension
    slotAddedDynamicExtension = slots.slot_added_dynamic_extension
    slotBeforeChangeDocument = slots.slot_before_change_document
    slotChangedDocument = slots.slot_changed_document
    slotRelabelDocument = slots.slot_relabel_document
    slotUndoDocument = slots.slot_undo_document
    slotRedoDocument = slots.slot_redo_document
    slotUndo = slots.slot_undo
    slotRedo = slots.slot_redo
    slotBeforeRecomputeDocument = slots.slot_before_recompute_document
    slotRecomputedDocument = slots.slot_recomputed_document
    slotRecomputedObject = slots.slot_recomputed_object
    slotOpenTransaction = slots.slot_open_transaction
    slotCommitTransaction = slots.slot_commit_transaction
    slotAbortTransaction = slots.slot_abort_transaction
    slotBeforeCloseTransaction = slots.slot_before_close_transaction
    slotCloseTransaction = slots.slot_close_transaction
    slotStartSaveDocument = slots.slot_start_save_document
    slotFinishSaveDocument = slots.slot_finish_save_document
    slotDeletedDocument = slots.slot_deleted_document
