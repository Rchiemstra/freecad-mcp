"""Invalid save request error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class InvalidSaveRequestError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "INVALID_SAVE_REQUEST"
