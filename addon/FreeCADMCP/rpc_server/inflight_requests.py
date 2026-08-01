"""Process-wide authenticated request cancellation and completion tracking.

The registry deliberately has no FreeCAD or Qt dependency.  It spans the
whole ``invoke_v2`` lifetime, including filesystem/worker gaps and GUI work
that finishes after its XML-RPC handler has returned.
"""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .inflight_requests_ops.cancellation_result import CancellationResult  # noqa: F401
from .inflight_requests_ops.cancellation_token import CancellationToken  # noqa: F401
from .inflight_requests_ops.inflight_lease_credential import (  # noqa: F401
    InflightLeaseCredential,
)
from .inflight_requests_ops.inflight_request import InflightRequest  # noqa: F401
from .inflight_requests_ops.inflight_request_registry import (  # noqa: F401
    InflightRequestRegistry,
)
from .inflight_requests_ops.inflight_snapshot import InflightSnapshot  # noqa: F401
from .inflight_requests_ops.request_cancellation_error import (  # noqa: F401
    RequestCancellationError,
)
