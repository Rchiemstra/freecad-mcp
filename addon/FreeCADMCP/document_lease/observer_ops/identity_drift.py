"""Identity drift inspection helpers for live document registration."""

from __future__ import annotations

from typing import Any


def identity_refresh_refusal_code(exc: BaseException) -> str:
    message = str(exc).lower()
    if "content hash" in message:
        return "IDENTITY_REFRESH_CONTENT_HASH_CHANGED"
    if "name or canonical path" in message or "name or path" in message:
        return "IDENTITY_REFRESH_NAME_OR_PATH_CHANGED"
    if "baseline is missing" in message or (
        "baseline" in message and "missing" in message
    ):
        return "IDENTITY_REFRESH_BASELINE_MISSING"
    if (
        "not a registered live document proxy" in message
        or "replacement proxy" in message
    ):
        return "IDENTITY_REFRESH_REPLACEMENT_PROXY"
    if "lease state" in message or "current lease state" in message:
        return "IDENTITY_REFRESH_LEASE_STATE_FORBIDS"
    code = str(getattr(exc, "code", "") or "").strip()
    if code:
        return code
    return "IDENTITY_REFRESH_REFUSED"


def collect_identity_drift_fields(identities: Any, document: Any) -> tuple[str, ...]:
    registered_session_uuid = getattr(identities, "registered_session_uuid", None)
    if not callable(registered_session_uuid):
        return ()
    try:
        session_uuid = registered_session_uuid(document)
    except Exception as exc:
        if (
            type(exc).__name__ == "UnknownDocumentError"
            or "not a registered live document proxy" in str(exc).casefold()
        ):
            return ("unregistered_proxy",)
        raise
    try:
        observed = identities.inspect_registered_document(session_uuid, document)
    except Exception as exc:
        if "not the registered live document proxy" in str(exc):
            return ("replacement_proxy",)
        return ("live_proxy_inspection_failed",)
    try:
        expected = identities.resolve(session_uuid)
    except Exception:
        return ("registered_identity_unavailable",)
    drifted: list[str] = []
    if observed.name != expected.name:
        drifted.append("name")
    if observed.comparison_key != expected.comparison_key:
        drifted.append("comparison_key")
    if observed.file_identity != expected.file_identity:
        drifted.append("file_identity")
    return tuple(drifted)
