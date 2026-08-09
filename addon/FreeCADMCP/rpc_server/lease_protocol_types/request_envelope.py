"""Compatibility import for the canonical request envelope."""

try:
    from ..._shared.protocol.request_envelope import RequestEnvelope
except ImportError:
    from _shared.protocol.request_envelope import RequestEnvelope

__all__ = ["RequestEnvelope"]
