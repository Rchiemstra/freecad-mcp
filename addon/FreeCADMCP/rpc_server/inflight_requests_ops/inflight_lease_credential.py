"""Compatibility import for the canonical private lease credential."""

try:
    from ...dispatch.inflight_lease_credential import InflightLeaseCredential
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.inflight_lease_credential import InflightLeaseCredential

__all__ = ["InflightLeaseCredential"]
