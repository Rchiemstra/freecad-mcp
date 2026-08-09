"""Paths (Phase 7 / 7D server_ops)."""

from __future__ import annotations

import os


def path_identity(value: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(value)))
