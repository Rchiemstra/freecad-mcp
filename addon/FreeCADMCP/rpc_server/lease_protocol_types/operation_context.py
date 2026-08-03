"""Compatibility import for the canonical operation context."""

try:
    from ..._shared.protocol.operation_context import OperationContext
except ImportError:
    from _shared.protocol.operation_context import OperationContext

__all__ = ["OperationContext"]
