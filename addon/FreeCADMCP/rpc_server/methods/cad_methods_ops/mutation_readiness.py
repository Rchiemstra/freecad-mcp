"""Read-only document mutation readiness and document-local quarantine."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from typing import Any

try:
    from automation_pause import status as automation_pause_status
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause import status as automation_pause_status

_QUARANTINED: dict[tuple[str, int, str], str] = {}

_NATIVE_BOOLEAN_FIELDS = frozenset(
    {
        "ready",
        "stable_event_supported",
        "pending_transaction",
        "transaction_locked",
        "recomputing",
        "must_execute",
        "pending_removal",
        "commit_barrier",
        "notification_replay",
        "poisoned",
        "quarantined",
    }
)
_NATIVE_AUTHORITATIVE_FIELDS = _NATIVE_BOOLEAN_FIELDS | {
    "booked_transaction",
    "diagnostic",
}


def _lifecycle_key(document: Any) -> tuple[str, int, str]:
    """Identify one live document instance, not a reusable document name."""

    name = str(getattr(document, "Name", "") or "")
    uid = str(getattr(document, "Uid", "") or "")
    return (name, id(document), uid)


def mark_quarantined(document: Any, diagnostic: str) -> None:
    if document is not None:
        _QUARANTINED[_lifecycle_key(document)] = str(diagnostic)[:1024]


def clear_quarantine(document: Any) -> None:
    """Clear only the matching live lifecycle after a verified safe recovery."""

    _QUARANTINED.pop(_lifecycle_key(document), None)


def prune_closed_quarantines(documents: Any) -> None:
    live = {_lifecycle_key(document) for document in documents}
    for key in tuple(_QUARANTINED):
        if key not in live:
            _QUARANTINED.pop(key, None)


def _bounded_diagnostic(message: Any) -> str:
    return str(message or "native readiness diagnostic unavailable")[:1024]


def _native_readiness_snapshot(  # noqa: C901
    document: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return validated native readiness or an incompatibility diagnostic.

    The native collaboration lane requires a callable
    ``getMutationReadiness``.  Legacy attribute probes cannot prove the commit
    barrier, notification replay, poison, or quarantine fields, so absence and
    every malformed/failed advertised result are equally fail-closed.
    """

    try:
        getter = getattr(document, "getMutationReadiness", None)
    except Exception as exc:
        return (
            None,
            _bounded_diagnostic(
                "getMutationReadiness attribute access raised "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    if not callable(getter):
        return (
            None,
            "document does not provide callable getMutationReadiness(); "
            "native mutation readiness is required",
        )
    try:
        candidate = getter()
    except Exception as exc:
        return (
            None,
            _bounded_diagnostic(
                "getMutationReadiness() raised "
                f"{type(exc).__name__}: {exc}"
            ),
        )
    if not isinstance(candidate, Mapping):
        return (
            None,
            _bounded_diagnostic(
                "getMutationReadiness() returned "
                f"{type(candidate).__name__}; expected a mapping"
            ),
        )
    try:
        snapshot = dict(candidate)
    except Exception as exc:
        return (
            None,
            _bounded_diagnostic(
                "getMutationReadiness() mapping could not be copied: "
                f"{type(exc).__name__}: {exc}"
            ),
        )

    missing = sorted(_NATIVE_AUTHORITATIVE_FIELDS.difference(snapshot))
    invalid = sorted(
        field
        for field in _NATIVE_BOOLEAN_FIELDS
        if field in snapshot and not isinstance(snapshot[field], bool)
    )
    booked = snapshot.get("booked_transaction")
    if "booked_transaction" in snapshot and (
        isinstance(booked, bool) or not isinstance(booked, int) or booked < 0
    ):
        invalid.append("booked_transaction")
    if "diagnostic" in snapshot and not isinstance(snapshot["diagnostic"], str):
        invalid.append("diagnostic")

    consistency_error = ""
    if not missing and not invalid:
        if snapshot["stable_event_supported"] is not True:
            consistency_error = (
                "stable_event_supported must be true for event-driven admission"
            )
        else:
            expected_ready = not bool(
                snapshot["pending_transaction"]
                or snapshot["booked_transaction"]
                or snapshot["transaction_locked"]
                or snapshot["recomputing"]
                or snapshot["must_execute"]
                or snapshot["pending_removal"]
                or snapshot["commit_barrier"]
                or snapshot["notification_replay"]
                or snapshot["poisoned"]
                or snapshot["quarantined"]
            )
            if snapshot["ready"] is not expected_ready:
                consistency_error = (
                    "ready contradicts the authoritative blocker fields"
                )

    if missing or invalid or consistency_error:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if invalid:
            details.append("invalid " + ", ".join(sorted(set(invalid))))
        if consistency_error:
            details.append(consistency_error)
        native_diagnostic = snapshot.get("diagnostic")
        if isinstance(native_diagnostic, str) and native_diagnostic:
            details.append(f"native diagnostic: {native_diagnostic}")
        return (
            None,
            _bounded_diagnostic(
                "getMutationReadiness() returned malformed data: "
                + "; ".join(details)
            ),
        )
    return snapshot, None


def _unavailable_readiness(
    document: Any,
    *,
    diagnostic: str,
) -> dict[str, Any]:
    name = str(getattr(document, "Name", "") or "")
    lifecycle_key = _lifecycle_key(document)
    pause = automation_pause_status()
    reasons = []
    if lifecycle_key in _QUARANTINED:
        reasons.append("document_quarantined")
    reasons.append("native_readiness_unavailable")
    if pause["paused"]:
        reasons.append("automation_paused")
    local_diagnostic = _QUARANTINED.get(lifecycle_key, "")
    combined_diagnostic = diagnostic
    if local_diagnostic:
        combined_diagnostic = f"{local_diagnostic}; {diagnostic}"
    return {
        "document": name,
        "ready": False,
        "stable_event_supported": False,
        "reasons": reasons,
        "pending_transaction": None,
        "booked_transaction_id": None,
        "transaction_locked": None,
        "must_execute": None,
        "pending_removal": None,
        "recomputing": None,
        "collaboration_blocked": None,
        "commit_barrier": None,
        "notification_replay": None,
        "collaboration_poisoned": None,
        "automation_paused": pause["paused"],
        "pause_after_current": pause["pause_after_current"],
        "active_write_count": pause["active_write_count"],
        "current_operation": pause["current_operation"],
        "quarantined": lifecycle_key in _QUARANTINED,
        "native_readiness_available": False,
        "runtime_compatible": False,
        "diagnostic": _bounded_diagnostic(combined_diagnostic),
    }


def document_readiness(document: Any) -> dict[str, Any]:  # noqa: C901
    name = str(getattr(document, "Name", "") or "")
    lifecycle_key = _lifecycle_key(document)
    native_readiness, native_failure = _native_readiness_snapshot(document)
    if native_failure:
        return _unavailable_readiness(document, diagnostic=native_failure)
    if native_readiness is None:  # Defensive: the helper is fail-closed.
        return _unavailable_readiness(
            document,
            diagnostic="native mutation readiness is unavailable",
        )
    pending = bool(native_readiness["pending_transaction"])
    booked = native_readiness["booked_transaction"]
    try:
        booked = int(booked) if booked is not None else None
    except (TypeError, ValueError):
        booked = None
    locked = bool(native_readiness["transaction_locked"])
    must_execute = bool(native_readiness["must_execute"])
    pending_removal = bool(native_readiness["pending_removal"])
    poisoned = bool(native_readiness["poisoned"])
    barrier = bool(native_readiness["notification_replay"])
    commit_barrier = bool(native_readiness.get("commit_barrier", False))
    recomputing = bool(native_readiness["recomputing"])
    native_ready = native_readiness.get("ready")
    native_ready_false = native_ready is False
    pause = automation_pause_status()
    reasons: list[str] = []
    if lifecycle_key in _QUARANTINED or bool(native_readiness.get("quarantined", False)):
        reasons.append("document_quarantined")
    if pending or booked not in (None, 0) or locked:
        reasons.append("native_transaction_in_progress")
    if recomputing:
        reasons.append("native_recomputing")
    if must_execute:
        reasons.append("pending_recompute")
    if pending_removal:
        reasons.append("pending_object_removal")
    if barrier or commit_barrier:
        reasons.append("collaboration_notifications_replaying")
    if poisoned:
        reasons.append("collaboration_commit_poisoned")
    if native_ready_false:
        reasons.append("native_not_ready")
    if pause["paused"]:
        reasons.append("automation_paused")
    diagnostic = _QUARANTINED.get(lifecycle_key, "") or str(
        native_readiness.get("diagnostic") or ""
    )
    native_diagnostic = getattr(document, "collaborationCommitPoisonDiagnostic", None)
    if not diagnostic and callable(native_diagnostic):
        with suppress(Exception):
            diagnostic = str(native_diagnostic() or "")
    return {
        "document": name,
        "ready": not reasons and not native_ready_false,
        "stable_event_supported": True,
        "reasons": reasons,
        "pending_transaction": pending,
        "booked_transaction_id": booked,
        "transaction_locked": locked,
        "must_execute": must_execute,
        "pending_removal": pending_removal,
        "recomputing": recomputing,
        "collaboration_blocked": barrier or commit_barrier,
        "commit_barrier": commit_barrier,
        "notification_replay": barrier,
        "collaboration_poisoned": poisoned,
        "automation_paused": pause["paused"],
        "pause_after_current": pause["pause_after_current"],
        "active_write_count": pause["active_write_count"],
        "current_operation": pause["current_operation"],
        "quarantined": lifecycle_key in _QUARANTINED
        or bool(native_readiness.get("quarantined", False)),
        "native_readiness_available": True,
        "runtime_compatible": True,
        "diagnostic": diagnostic or None,
    }


def get_mutation_readiness(self, doc_name: str | None = None) -> dict[str, Any]:
    freecad = self._cad_collaborators.freecad
    result = self._dispatch_gui(
        lambda: get_mutation_readiness_gui(freecad=freecad, doc_name=doc_name)
    )
    return result if isinstance(result, dict) else {
        "success": False,
        "error_code": "READINESS_INSPECTION_FAILED",
        "error": str(result),
    }


def get_mutation_readiness_gui(*, freecad: Any, doc_name: str | None = None) -> dict[str, Any]:
    """Capture native readiness atomically on FreeCAD's GUI thread."""

    documents = freecad.listDocuments()
    prune_closed_quarantines(documents.values())
    if doc_name:
        document = documents.get(doc_name) or freecad.getDocument(doc_name)
        if document is None:
            return {
                "success": False,
                "error_code": "DOCUMENT_NOT_FOUND",
                "error": f"Document '{doc_name}' not found",
            }
        item = document_readiness(document)
        return {
            "success": True,
            "ready": item["ready"],
            "documents": [item],
            "reasons": item["reasons"],
            "automation_pause": automation_pause_status(),
        }
    items = [document_readiness(document) for document in documents.values()]
    reasons = sorted({reason for item in items for reason in item["reasons"]})
    return {
        "success": True,
        "ready": not reasons,
        "documents": items,
        "reasons": reasons,
        "automation_pause": automation_pause_status(),
    }
