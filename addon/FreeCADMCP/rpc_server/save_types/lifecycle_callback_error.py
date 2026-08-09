"""Save lifecycle callback error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class LifecycleCallbackError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "SAVE_LIFECYCLE_CALLBACK_FAILED"
