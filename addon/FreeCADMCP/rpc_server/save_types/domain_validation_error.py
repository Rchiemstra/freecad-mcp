"""Domain validation error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class DomainValidationError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "SAVE_DOMAIN_VALIDATION_FAILED"
