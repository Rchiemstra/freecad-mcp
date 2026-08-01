from __future__ import annotations

import os
from pathlib import Path

from .doc_key_resolver import _doc_key_for_document
from .eligibility import _is_eligible_target
from .facade_surfaces import current_time
from .file_baseline import verify_saved_file
from .gui_callback import _notify_gui
from .internal_snapshot_save_ops import is_internal_snapshot_save
from .lease_state import LeaseState
from .mark_user_intervened import mark_user_intervened
from .migrate_lease_key import migrate_lease_key
from .registry_state import _pending_saves, _registry, _registry_lock, _session_ids
from .request_identity import is_agent_mutating
from .settings import is_enabled
from .sidecar_io import _create_sidecar_exclusive, _remove_sidecar, sidecar_path_for
from .transition_lease import transition_lease


def _finish_save_lookup(doc_name: str, dest: str) -> str | None:
    with _registry_lock:
        _pending_saves.pop(doc_name, None)
        for key, rec in list(_registry.items()):
            if rec.doc_name == doc_name or key == dest:
                return key
    return None


def _apply_finish_save(doc_name: str, dest: str, old_key: str) -> None:
    verify = verify_saved_file(dest)
    if not verify.get("ok"):
        with _registry_lock:
            if old_key in _registry:
                _registry[old_key].state = LeaseState.LOCKED_ERROR.value
        _notify_gui()
        return
    if old_key != dest:
        migrate_lease_key(old_key, dest, doc_name=doc_name)
        _notify_gui()
        return
    with _registry_lock:
        token = _registry[dest].token if dest in _registry else ""
    if token:
        transition_lease(
            dest,
            token,
            LeaseState.LOCKED_IDLE.value,
            current_operation="",
            document_dirty=False,
        )
    _notify_gui()


class DocumentLockObserver:
    """Detects user edits on locked docs and migrates leases on save."""

    def slotChangedObject(self, obj, prop):
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotCreatedObject(self, obj):
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotDeletedObject(self, obj):
        self._maybe_user_edit(getattr(obj, "Document", None))

    def slotStartSaveDocument(self, document, filename):
        if is_internal_snapshot_save(document, filename):
            return
        if not is_enabled():
            return
        if not filename or not _is_eligible_target(filename):
            return
        dest = str(Path(filename).resolve())
        doc_name = getattr(document, "Name", "") or ""
        old_key = _doc_key_for_document(document)
        with _registry_lock:
            _pending_saves[doc_name] = dest
            record = _registry.get(old_key) if old_key else None
        if record is None:
            return
        side = sidecar_path_for(dest)
        if not side.is_file():
            pre = dict(record.to_sidecar_dict())
            pre["doc_key"] = dest
            pre["state"] = LeaseState.LOCKED_SAVING.value
            pre["last_heartbeat"] = current_time()
            _create_sidecar_exclusive(side, pre)
        with _registry_lock:
            if old_key and old_key in _registry:
                _registry[old_key].state = LeaseState.LOCKED_SAVING.value
                _registry[old_key].current_operation = f"saving:{dest}"
        _notify_gui()

    def slotFinishSaveDocument(self, document, filename):
        if is_internal_snapshot_save(document, filename):
            return
        if not is_enabled():
            return
        if not filename or not _is_eligible_target(filename):
            return
        dest = str(Path(filename).resolve())
        doc_name = getattr(document, "Name", "") or ""
        old_key = _finish_save_lookup(doc_name, dest)
        if old_key is None:
            return
        _apply_finish_save(doc_name, dest, old_key)

    def slotDeletedDocument(self, document):
        if not is_enabled():
            return
        key = _doc_key_for_document(document)
        name = getattr(document, "Name", None)
        with _registry_lock:
            if name:
                _session_ids.pop(name, None)
                _pending_saves.pop(name, None)
            if key and key in _registry:
                rec = _registry.pop(key, None)
                if rec and os.path.isabs(key) and key.lower().endswith(".fcstd"):
                    _remove_sidecar(sidecar_path_for(key))
        _notify_gui()

    def _maybe_user_edit(self, document) -> None:
        if not is_enabled():
            return
        key = _doc_key_for_document(document)
        if not key:
            return
        if is_agent_mutating(key):
            return
        name = getattr(document, "Name", None)
        if name and is_agent_mutating(name):
            return
        with _registry_lock:
            if key not in _registry:
                return
        mark_user_intervened(key)
        _notify_gui()
