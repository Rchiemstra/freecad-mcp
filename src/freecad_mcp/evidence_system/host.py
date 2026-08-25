"""Portable host-interpreter selection; the selector is never inherited."""
from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
from typing import Mapping

from .launch_source import LaunchSourceError


SELECTOR = "FREECAD_MCP_EVIDENCE_PYTHON"


def select_host_interpreter(source: Mapping[str, str] | None = None) -> Path:
    values = os.environ if source is None else source
    raw = values.get(SELECTOR)
    # The ambient default is normalized only after it is selected.  An
    # explicit selector deliberately stays lexical so its own reparse points
    # are still rejected by the walk below.
    path = Path(raw).expanduser() if raw else Path(sys.executable).resolve()
    if not path.is_absolute():
        raise LaunchSourceError("interpreter", "HOST_INTERPRETER_RELATIVE", "host-interpreter", "/path")
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            details = os.lstat(current)
        except OSError as error:
            raise LaunchSourceError("interpreter", "HOST_INTERPRETER_MISSING", "host-interpreter", "/path") from error
        if stat.S_ISLNK(details.st_mode) or getattr(details, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise LaunchSourceError("interpreter", "HOST_INTERPRETER_REPARSE", "host-interpreter", "/path")
    if not path.is_file():
        raise LaunchSourceError("interpreter", "HOST_INTERPRETER_MISSING", "host-interpreter", "/path")
    return path
