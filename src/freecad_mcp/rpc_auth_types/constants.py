"""Protocol constants for authenticated RPC v2 (MCP client side)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

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

MAX_HANDSHAKE_BYTES = 64 * 1024

MAX_INSTANCE_MANIFEST_BYTES = 64 * 1024

MAX_SECRET_FILE_BYTES = 4096

MIN_SECRET_BYTES = 32

MAX_JSON_DEPTH = 32

MAX_ACCEPTED_SESSION_LIFETIME_SECONDS = 60 * 60 + 30

_PROCESS_STARTED_AT = datetime.now(UTC)

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+\-=]{0,255}$")

_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{22,128}$")

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,512}$")

_PROOF_RE = re.compile(r"^hmac-sha256:([0-9a-f]{64})$")

_REQUEST_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-request\x00"

_RESPONSE_PROOF_DOMAIN = b"freecad-mcp-rpc-v2\x00handshake-response\x00"

