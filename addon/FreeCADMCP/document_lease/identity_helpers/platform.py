"""Platform name normalization for document identity path policy."""

from __future__ import annotations

import os


def platform_name(platform: str | None = None) -> str:
    value = (platform or ("windows" if os.name == "nt" else "posix")).lower()
    return "windows" if value.startswith("win") or value == "nt" else "posix"
