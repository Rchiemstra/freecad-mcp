"""Extracted ``RpcAuthError`` for ARCH002 (workstream 1G)."""

from __future__ import annotations


class RpcAuthError(ValueError):
    """A bounded authentication failure with a stable public error code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.public_message = str(message)
        super().__init__(f"{self.code}: {self.public_message}")


RpcAuthError.__module__ = "freecad_mcp.rpc_auth"
