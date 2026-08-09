"""Document remains dirty after save error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class DocumentDirtyError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "DOCUMENT_REMAINS_DIRTY"
