"""FreeCAD save invocation error."""

from __future__ import annotations

from .save_service_error import SaveServiceError


class SaveInvocationError(SaveServiceError):
    __module__ = "rpc_server.save_service"
    code = "FREECAD_SAVE_FAILED"
