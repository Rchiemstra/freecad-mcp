import hashlib
import hmac
import json
from dataclasses import replace

from ..mutation_guard import RollbackCoverage, make_method_spec, validate_document_invariants

try:
    from ..._shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
except ImportError:  # pragma: no cover - flat addon import path
    from _shared.protocol.protocol_error import ProtocolError as LeaseProtocolError

"""Generated execute_code envelope helpers."""

def _generated_execute_signature(
    *,
    session_token,
    request_id,
    code,
    options,
):
    affected = options.get("affected_documents") or ()
    payload = {
        "request_id": str(request_id or ""),
        "operation_id": str(options.get("operation_id") or ""),
        "code_sha256": hashlib.sha256(str(code).encode("utf-8")).hexdigest(),
        "document": str(options.get("document") or ""),
        "affected_documents": sorted({str(item) for item in affected}),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(str(session_token).encode("utf-8"), canonical, hashlib.sha256)
    return f"hmac-sha256:{digest.hexdigest()}"


def _validate_generated_operation_envelope(envelope):
    """Authenticate session-derived execute metadata before replay lookup.

    The signature rotates with the RPC session and is intentionally omitted
    from the semantic request fingerprint.  Omitting it is safe only after the
    current envelope has independently proved the capability.
    """

    if envelope.method != "execute_code":
        return
    options = envelope.params.get("options")
    if not isinstance(options, dict) or not options.get("generated_operation"):
        return
    code = envelope.params.get("code")
    operation_id = str(options.get("operation_id") or "")
    supplied = str(options.get("operation_signature") or "")
    if not isinstance(code, str) or not operation_id or not supplied:
        raise LeaseProtocolError(
            "GENERATED_OPERATION_SIGNATURE_INVALID",
            "The generated-operation capability signature is missing or invalid",
        )
    expected = _generated_execute_signature(
        session_token=envelope.session_token,
        request_id=envelope.request_id,
        code=code,
        options=options,
    )
    if not hmac.compare_digest(supplied, expected):
        raise LeaseProtocolError(
            "GENERATED_OPERATION_SIGNATURE_INVALID",
            "The generated-operation capability signature is missing or invalid",
        )


def _generated_operation_method_spec(base_spec, operation_id):
    """Specialize signed ``execute_code`` as its typed operation.

    In particular, a generated typed operation must inherit the typed method's
    recovery permission instead of the generic arbitrary-code prohibition.
    """

    generated_spec = make_method_spec(operation_id, "MUTATING")
    return replace(
        base_spec,
        name=operation_id,
        validator=validate_document_invariants,
        allowed_during_recovery=generated_spec.allowed_during_recovery,
        rollback_coverage=RollbackCoverage.DOCUMENT_ONLY,
    )
