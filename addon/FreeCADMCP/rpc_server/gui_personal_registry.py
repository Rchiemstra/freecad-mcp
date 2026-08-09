"""Transient actor navigation metadata outside global GUI authority."""

from __future__ import annotations

import threading


class PersonalViewRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._active_targets = {}
        self._metadata = {}

    def activate(self, actor_id, document_name, metadata=None):
        with self._lock:
            self._active_targets[str(actor_id)] = str(document_name)
            if metadata:
                key = (str(actor_id), str(document_name))
                current = dict(self._metadata.get(key, {}))
                current.update(dict(metadata))
                self._metadata[key] = current

    def current_target(self, actor_id):
        with self._lock:
            return self._active_targets.get(str(actor_id))

    def restore_target(self, actor_id, document_name):
        with self._lock:
            actor = str(actor_id)
            if document_name is None:
                self._active_targets.pop(actor, None)
            else:
                self._active_targets[actor] = str(document_name)

    def remember(self, actor_id, document_name, metadata):
        with self._lock:
            key = (str(actor_id), str(document_name))
            current = dict(self._metadata.get(key, {}))
            for name, value in dict(metadata or {}).items():
                current.setdefault(name, value)
            self._metadata[key] = current

    def metadata(self, actor_id, document_name):
        with self._lock:
            return dict(self._metadata.get((str(actor_id), str(document_name)), {}))


__all__ = ["PersonalViewRegistry"]
