"""Compatibility imports for canonical protocol proof helpers."""

try:
    from ..._shared.protocol.proof import _proof, _verify_proof
except ImportError:
    from _shared.protocol.proof import _proof, _verify_proof

__all__ = ["_proof", "_verify_proof"]
