from __future__ import annotations

import threading

from .lease_record import LeaseRecord
from .module_aliases import install_module_aliases

_registry: dict[str, LeaseRecord] = {}
_registry_lock = threading.Lock()
# Document.Name → session UUID for unsaved docs
_session_ids: dict[str, str] = {}
# Pending Save As migrations: doc_name → destination path being written
_pending_saves: dict[str, str] = {}

install_module_aliases(__name__)
