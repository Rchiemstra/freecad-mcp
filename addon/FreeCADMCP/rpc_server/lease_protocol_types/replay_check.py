"""Extracted ``ReplayCheck`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayCheck:
    status: str
    response: Any = None


ReplayCheck.__module__ = "rpc_server.lease_protocol"
