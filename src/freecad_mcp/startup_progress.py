"""Optional launch-scoped startup hints; never evidence of RPC identity."""

import os
from pathlib import Path

STARTUP_PROGRESS_ENV = "FREECAD_MCP_STARTUP_PROGRESS_DIR"
STARTUP_PHASES = ("addon-imported", "gui-ready", "rpc-listening")
DEFAULT_RPC_WAIT_TIMEOUT = 900.0


def record_startup_phase(phase: str) -> None:
    directory = os.environ.get(STARTUP_PROGRESS_ENV)
    if not directory or phase not in STARTUP_PHASES:
        return
    try:
        # Only the launcher creates this directory, inside its isolated profile.
        # Each launch gets a fresh path; ordinary FreeCAD starts write nothing.
        (Path(directory) / phase).touch(exist_ok=True)
    except OSError:
        pass  # Progress hints must never interfere with startup.
