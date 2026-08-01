"""Runtime paths and version identity for worker admission."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerRuntime:
    gui_executable: str
    freecad_home: str
    gui_version: tuple[str, str, str, str]
    configured_path: str = ""
