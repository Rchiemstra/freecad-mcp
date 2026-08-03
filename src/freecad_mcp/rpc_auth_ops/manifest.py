"""Compatibility exports for canonical runtime manifest operations."""

from __future__ import annotations

from .._shared.protocol.manifest import (
    load_instance_manifest,
    make_mcp_runtime_identity,
)

__all__ = [
    "load_instance_manifest",
    "make_mcp_runtime_identity",
]
