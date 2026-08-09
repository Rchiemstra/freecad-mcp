"""GUI-thread save invocation capture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SaveInvocation:
    """GUI-thread result captured immediately after FreeCAD writes the file."""

    mode: str
    path: str
    comparison_key: str
    previous_path: str | None
    validation_profile: str = "default"
    destination_preexisted: bool = False

SaveInvocation.__module__ = "rpc_server.save_service"
