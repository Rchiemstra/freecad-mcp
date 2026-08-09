"""Canonical constants for authenticated FreeCAD MCP RPC protocol v2."""

from __future__ import annotations

import re as _re
from datetime import UTC as _UTC
from datetime import datetime as _datetime

PROTOCOL_NAME = "freecad-mcp-rpc"

PROTOCOL_VERSION = 2

HANDSHAKE_REQUEST_KIND = "freecad-mcp-handshake-v2"

HANDSHAKE_RESPONSE_KIND = "freecad-mcp-handshake-v2-response"

HMAC_ALGORITHM = "hmac-sha256"

INSTANCE_MANIFEST_SCHEMA_VERSION = 1

SUPPORTED_FEATURES = (
    "authenticated_sessions",
    "document_session_identity",
    "lease_credentials_v2",
    "request_idempotency",
    "runtime_binding",
)

REQUIRED_PROTOCOL_FEATURES = frozenset(
    {
        "authenticated_sessions",
        "lease_credentials_v2",
        "runtime_binding",
    }
)

DEFAULT_SESSION_TTL_SECONDS = 5 * 60.0

MAX_SESSION_TTL_SECONDS = 60 * 60.0

DEFAULT_REPLAY_TTL_SECONDS = 10 * 60.0

DEFAULT_REPLAY_RESPONSE_MAX_BYTES = 64 * 1024

MAX_HANDSHAKE_BYTES = 64 * 1024

MAX_ENVELOPE_BYTES = 1024 * 1024

MAX_INSTANCE_MANIFEST_BYTES = 64 * 1024

MAX_SECRET_FILE_BYTES = 4096

MIN_SECRET_BYTES = 32

MAX_LEASE_CREDENTIALS = 32

MAX_PARAMS_DEPTH = 32

MAX_JSON_DEPTH = MAX_PARAMS_DEPTH

MAX_HANDSHAKE_NONCES = 65_536

MAX_ACCEPTED_SESSION_LIFETIME_SECONDS = 60 * 60 + 30

_PROCESS_STARTED_AT = _datetime.now(_UTC)

_METHOD_RE = _re.compile(r"^[a-z][a-z0-9_]{0,127}$")

_SAFE_IDENTIFIER_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}$")

_NONCE_RE = _re.compile(r"^[A-Za-z0-9_-]{22,128}$")

_TOKEN_RE = _re.compile(r"^[A-Za-z0-9_-]{32,512}$")

_PROOF_RE = _re.compile(r"^hmac-sha256:([0-9a-f]{64})$")

_REQUEST_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-request\x00"

_RESPONSE_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-response\x00"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "auth_secret",
        "credential",
        "credentials",
        "hmac",
        "lease_token",
        "password",
        "proof",
        "secret",
        "secret_fingerprint",
        "session_token",
        "token",
        "token_digest",
        "token_fingerprint",
    }
)

_REDACTED = "<redacted>"
