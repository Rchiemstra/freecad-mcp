"""Extracted ``RequestEnvelope`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    _METHOD_RE,
    _REDACTED,
    MAX_ENVELOPE_BYTES,
    MAX_LEASE_CREDENTIALS,
    PROTOCOL_VERSION,
)
from .lease_credential import LeaseCredential
from .operation_context import OperationContext
from .protocol_error import ProtocolError
from .redaction import redact_sensitive
from .validation import (
    _limited_canonical_json,
    _require_exact_keys,
    _require_sequence,
    _require_uuid,
    _token_digest,
    _validate_token,
    canonical_json_bytes,
)


@dataclass(frozen=True)
class RequestEnvelope:
    request_id: str
    session_token: str = field(repr=False)
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict, repr=False)
    lease_credentials: tuple[LeaseCredential, ...] = ()
    operation: OperationContext | None = None
    mcp_runtime_id: str | None = None
    protocol_version: int = PROTOCOL_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RequestEnvelope:
        if not isinstance(payload, Mapping):
            raise ProtocolError(
                "MALFORMED_ENVELOPE", "Authenticated RPC envelope must be an object"
            )
        _limited_canonical_json(dict(payload), MAX_ENVELOPE_BYTES, "ENVELOPE_TOO_LARGE")
        _require_exact_keys(
            payload,
            required={
                "protocol_version",
                "request_id",
                "session_token",
                "method",
                "params",
                "lease_credentials",
            },
            optional={"operation", "mcp_runtime_id"},
            context="authenticated RPC envelope",
        )
        if payload["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError(
                "UNSUPPORTED_PROTOCOL", "Authenticated RPC protocol version is unsupported"
            )
        method = payload["method"]
        if not isinstance(method, str) or not _METHOD_RE.fullmatch(method):
            raise ProtocolError(
                "INVALID_METHOD", "Authenticated RPC method name is invalid"
            )
        params = payload["params"]
        if not isinstance(params, dict):
            raise ProtocolError(
                "MALFORMED_ENVELOPE", "Authenticated RPC params must be an object"
            )
        credentials_payload = _require_sequence(
            payload["lease_credentials"], "lease_credentials"
        )
        if len(credentials_payload) > MAX_LEASE_CREDENTIALS:
            raise ProtocolError(
                "TOO_MANY_LEASES", "Authenticated RPC request declares too many leases"
            )
        credentials = tuple(
            LeaseCredential.from_dict(item) for item in credentials_payload
        )
        lease_ids = {credential.lease_id for credential in credentials}
        document_ids = {
            credential.document_session_uuid for credential in credentials
        }
        if len(lease_ids) != len(credentials) or len(document_ids) != len(credentials):
            raise ProtocolError(
                "DUPLICATE_LEASE", "Authenticated RPC request repeats a lease or document"
            )
        operation_payload = payload.get("operation")
        mcp_runtime_id = payload.get("mcp_runtime_id")
        return cls(
            protocol_version=PROTOCOL_VERSION,
            request_id=_require_uuid(payload["request_id"], "request_id"),
            session_token=_validate_token(payload["session_token"], "session_token"),
            method=method,
            params=copy.deepcopy(params),
            lease_credentials=credentials,
            operation=None
            if operation_payload is None
            else OperationContext.from_dict(operation_payload),
            mcp_runtime_id=None
            if mcp_runtime_id is None
            else _require_uuid(mcp_runtime_id, "mcp_runtime_id"),
        )

    def semantic_fingerprint(self) -> str:
        """Fingerprint stable request semantics without renewable session data.

        Session tokens rotate during a normal authenticated reconnect.  The
        generated-operation capability signature is derived from that token,
        so it is likewise transport/session data rather than operation
        semantics.  The RPC boundary validates that signature against the
        current session *before* consulting the replay journal.
        """

        params = copy.deepcopy(self.params)
        if self.method == "execute_code":
            options = params.get("options")
            if isinstance(options, dict) and options.get("generated_operation"):
                options.pop("operation_signature", None)
        payload = {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "mcp_runtime_id": self.mcp_runtime_id,
            "method": self.method,
            "params": params,
            "lease_credentials": sorted(
                [
                {
                    "lease_id": item.lease_id,
                    "document_session_uuid": item.document_session_uuid,
                    "generation": item.generation,
                    "token_digest": _token_digest(item.token),
                }
                for item in self.lease_credentials
                ],
                key=lambda item: (
                    item["document_session_uuid"],
                    item["lease_id"],
                    item["generation"],
                ),
            ),
            "operation": None
            if self.operation is None
            else {"name": self.operation.name, "task_id": self.operation.task_id},
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    def fingerprint(self) -> str:
        """Compatibility alias for the stable semantic fingerprint."""

        return self.semantic_fingerprint()

    def redacted_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "session_token": _REDACTED,
            "mcp_runtime_id": self.mcp_runtime_id,
            "method": self.method,
            "params": redact_sensitive(self.params),
            "lease_credentials": [item.redacted_dict() for item in self.lease_credentials],
            "operation": None
            if self.operation is None
            else {"name": self.operation.name, "task_id": self.operation.task_id},
        }
