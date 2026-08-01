"""Save-as destination conflict error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class DestinationConflictError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "SAVE_AS_DESTINATION_CONFLICT"
