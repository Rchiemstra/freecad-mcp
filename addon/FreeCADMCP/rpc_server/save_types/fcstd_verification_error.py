"""FCStd archive verification error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class FcstdVerificationError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "FCSTD_VERIFICATION_FAILED"
