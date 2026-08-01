"""Disposable worker profile environment."""

from __future__ import annotations

import os
from pathlib import Path


def worker_environment(workspace: Path) -> dict[str, str]:
    """Return an inherited environment with a job-private FreeCAD profile."""

    profile = workspace / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["FREECAD_USER_HOME"] = str(profile)
    environment["FREECAD_USER_DATA"] = str(profile)
    return environment
