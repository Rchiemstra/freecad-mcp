import hashlib

from ..lease_protocol import redact_sensitive as redact_lease_protocol_details
from ..lease_runtime import _import_document_lock

"""RPC diagnostic redaction and lease error formatting."""

def _import_core_authority():
    """Import the core-authority bridge in addon and repository layouts."""
    try:
        from addon.FreeCADMCP.document_lease import core_authority as mod

        return mod
    except ImportError:
        from document_lease import core_authority as mod

        return mod


def _redact_rpc_diagnostic(value, *, identity=None, inflight=None):
    """Return bounded diagnostic text with exact request secrets removed."""

    if isinstance(value, (dict, list, tuple)):
        value = redact_lease_protocol_details(value)
    text = str(value)
    if identity is None:
        try:
            identity = _import_document_lock().get_request_identity()
        except Exception:
            identity = {}
    secrets = {
        str(identity.get("rpc_session_token") or ""),
        str(identity.get("lease_token") or ""),
    }
    for item in identity.get("lease_credentials") or ():
        if isinstance(item, dict):
            secrets.add(str(item.get("token") or ""))
    if inflight is not None:
        secrets.update(item.token for item in inflight.credentials)
    for secret in tuple(secrets):
        if not secret:
            continue
        fingerprint = "sha256:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()
        text = text.replace(secret, "<redacted>")
        text = text.replace(fingerprint, "<redacted>")
    return text[:2048]


def _lease_service_error(exc, *, request_id=None):
    """Convert lease-core failures to a bounded, token-free RPC result."""
    code = getattr(exc, "code", "LEASE_SERVICE_ERROR")
    result = {
        "success": False,
        "ok": False,
        "error_code": code,
        "error": _redact_rpc_diagnostic(exc),
    }
    details = getattr(exc, "details", None)
    if details:
        # Service errors may include nested coordination records. Keep this
        # boundary independently safe even if a future exception accidentally
        # carries a credential digest or bearer-token-shaped field.
        result["details"] = redact_lease_protocol_details(details)
    if request_id:
        result["request_id"] = request_id
    return result


def _format_identity_registration_error(failure) -> str:
    """Build a self-describing identity-registration failure message."""

    message = (
        f"live document identity for {failure.document_name!r} could not be "
        f"registered ({failure.failure_branch})"
    )
    if failure.drifted_fields:
        message += "; drifted field(s): " + ", ".join(failure.drifted_fields)
    if failure.identity_refresh_attempted:
        if failure.identity_refresh_refused_reason:
            message += (
                "; automatic identity refresh was attempted and refused "
                f"({failure.identity_refresh_refused_reason})"
            )
        else:
            message += "; automatic identity refresh was attempted"
    else:
        message += "; automatic identity refresh was not attempted"
    return message
