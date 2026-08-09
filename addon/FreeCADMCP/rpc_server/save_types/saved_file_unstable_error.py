"""Saved file unstable error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class SavedFileUnstableError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "SAVED_FILE_UNSTABLE"
