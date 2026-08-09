"""Compatibility import for the canonical lease credential."""

try:
    from ..._shared.protocol.lease_credential import LeaseCredential
except ImportError:
    from _shared.protocol.lease_credential import LeaseCredential

__all__ = ["LeaseCredential"]
