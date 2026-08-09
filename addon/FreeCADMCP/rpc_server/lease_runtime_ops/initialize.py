"""Frozen compatibility seam for the removed process-lifetime lease authority.

Native FreeCAD collaboration owns document authority after the Phase 18
cutover.  The historic bootstrap surface remains callable so legacy import
paths receive a deterministic no-op instead of constructing removed
sidecar or lease authority.
"""

from __future__ import annotations

from typing import Any


def initialize_document_lease_runtime(settings=None, *, rpc_mod: Any) -> None:
    """Retain the historic bootstrap surface as a frozen deprecation no-op."""

    del settings, rpc_mod
    return None
