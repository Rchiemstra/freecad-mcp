from __future__ import annotations

import json

_RECOMPUTE_LOG_SENTINEL = "__RECOMPUTE_LOG__"

def _format_recompute_log(output: str) -> str:
    """I3 — turn the `__RECOMPUTE_LOG__` JSON sentinel in the execute output into a
    compact human-readable summary. Returns '' when nothing is flagged (all Clean),
    so mutating tools that build cleanly stay quiet."""
    idx = output.rfind(_RECOMPUTE_LOG_SENTINEL)
    if idx < 0:
        return ""
    payload = output[idx + len(_RECOMPUTE_LOG_SENTINEL):]
    # The sentinel is the last printed line; trim any trailing addon chatter.
    payload = payload.strip().splitlines()[0] if payload.strip() else ""
    try:
        flagged = json.loads(payload) if payload else []
    except Exception:
        return ""
    if not flagged:
        return ""
    parts = []
    for e in flagged:
        mark = "" if e.get("valid", True) else " <INVALID>"
        parts.append(f"{e.get('name','?')} ({e.get('state','?')}){mark}")
    return "Recompute log (non-clean): " + ", ".join(parts)
