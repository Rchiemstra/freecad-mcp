from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _AgentMutationState:
    """Attribution owned by exactly one executing thread.

    FreeCAD document observers are called synchronously on the thread that is
    changing the live document.  Keeping this state thread-local therefore
    prevents an XML-RPC worker (or another GUI callback) from making unrelated
    changes look agent-authored.  Version-2 callers use one exact document-key
    set for the whole request.  The per-key counters exist solely for the
    compatibility facade used by version-1 integrations.
    """

    request_id: str = ""
    document_keys: frozenset[str] = frozenset()
    depth: int = 0
    violation: str = ""
    legacy_counts: dict[str, int] = field(default_factory=dict)
