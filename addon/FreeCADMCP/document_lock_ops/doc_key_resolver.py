from __future__ import annotations

from pathlib import Path

from .eligibility import _is_eligible_target
from .registry_state import _registry, _registry_lock, _session_ids


def _doc_key_for_document(document) -> str | None:
    if document is None:
        return None
    name = getattr(document, "Name", None)
    fname = getattr(document, "FileName", None) or ""
    if fname and _is_eligible_target(fname):
        return str(Path(fname).resolve())
    if name:
        with _registry_lock:
            sid = _session_ids.get(name)
            if sid:
                return sid
            # Also match by doc_name on any lease
            for key, rec in _registry.items():
                if rec.doc_name == name:
                    return key
    return None
