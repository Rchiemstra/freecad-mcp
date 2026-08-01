"""Path helpers for adjacent lease sidecar artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from .constants import GUARD_SUFFIX, SIDECAR_SUFFIX


def sidecar_path_for(document_path: str | os.PathLike[str]) -> Path:
    return Path(os.fspath(document_path) + SIDECAR_SUFFIX)


def guard_path_for(sidecar_path: str | os.PathLike[str]) -> Path:
    return Path(os.fspath(sidecar_path) + GUARD_SUFFIX)
