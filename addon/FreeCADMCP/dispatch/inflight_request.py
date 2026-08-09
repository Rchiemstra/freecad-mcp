"""One authenticated RPC request tracked by the inflight registry."""

from __future__ import annotations

from dataclasses import dataclass

from .cancellation_token import CancellationToken


@dataclass
class InflightRequest:
    session_id: str
    request_id: str
    method: str
    token: CancellationToken
