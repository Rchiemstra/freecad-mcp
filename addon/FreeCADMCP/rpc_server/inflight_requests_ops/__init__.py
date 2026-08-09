"""Compatibility package for canonical dispatch request-state objects."""

from .cancellation_result import CancellationResult
from .cancellation_token import CancellationToken
from .inflight_lease_credential import InflightLeaseCredential
from .inflight_request import InflightRequest
from .inflight_request_registry import InflightRequestRegistry
from .inflight_snapshot import InflightSnapshot
from .request_cancellation_error import RequestCancellationError

__all__ = [
    "CancellationResult",
    "CancellationToken",
    "InflightLeaseCredential",
    "InflightRequest",
    "InflightRequestRegistry",
    "InflightSnapshot",
    "RequestCancellationError",
]
