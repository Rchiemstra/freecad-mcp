"""Compatibility import for canonical runtime-manifest construction."""

from __future__ import annotations

try:
    from ..._shared.protocol.manifest import make_runtime_manifest
except ImportError:
    from _shared.protocol.manifest import make_runtime_manifest

__all__ = ["make_runtime_manifest"]
