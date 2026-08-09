"""Raised when worker jobs reference unsupported GUI APIs."""

from .protocol_error import ProtocolError


class UnsupportedWorkerGuiError(ProtocolError):
    pass
