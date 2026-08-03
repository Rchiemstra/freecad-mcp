"""Compatibility alias for the canonical protocol error."""

try:
    from ..._shared.protocol.protocol_error import (
        ProtocolError as LeaseProtocolError,
    )
    from ..._shared.protocol.protocol_error import (
        _is_uuid,
    )
except ImportError:
    from _shared.protocol.protocol_error import ProtocolError as LeaseProtocolError
    from _shared.protocol.protocol_error import _is_uuid

__all__ = ["LeaseProtocolError", "_is_uuid"]
