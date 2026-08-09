"""Baseline mismatch error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class BaselineMismatchError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "BASELINE_MISMATCH"
