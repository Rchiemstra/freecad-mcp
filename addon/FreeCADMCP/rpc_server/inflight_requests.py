"""Compatibility imports for the canonical dispatch request registry."""

try:
    from ..dispatch.cancellation_result import CancellationResult
    from ..dispatch.cancellation_token import CancellationToken
    from ..dispatch.inflight_lease_credential import InflightLeaseCredential
    from ..dispatch.inflight_request import InflightRequest
    from ..dispatch.inflight_request_registry import InflightRequestRegistry
    from ..dispatch.inflight_snapshot import InflightSnapshot
    from ..dispatch.request_cancellation_error import RequestCancellationError
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from dispatch.cancellation_result import CancellationResult
    from dispatch.cancellation_token import CancellationToken
    from dispatch.inflight_lease_credential import InflightLeaseCredential
    from dispatch.inflight_request import InflightRequest
    from dispatch.inflight_request_registry import InflightRequestRegistry
    from dispatch.inflight_snapshot import InflightSnapshot
    from dispatch.request_cancellation_error import RequestCancellationError

__all__ = [
    "CancellationResult",
    "CancellationToken",
    "InflightLeaseCredential",
    "InflightRequest",
    "InflightRequestRegistry",
    "InflightSnapshot",
    "RequestCancellationError",
]
