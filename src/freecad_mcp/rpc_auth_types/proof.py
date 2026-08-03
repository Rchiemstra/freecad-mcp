"""Compatibility exports for canonical HMAC proof helpers."""

from __future__ import annotations

from .._shared.protocol.proof import _proof, _verify_proof

__all__ = ["_proof", "_verify_proof"]
