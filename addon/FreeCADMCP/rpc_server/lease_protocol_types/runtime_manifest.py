"""Compatibility import for the canonical runtime manifest."""

try:
    from ..._shared.protocol.runtime_manifest import RuntimeManifest
except ImportError:
    from _shared.protocol.runtime_manifest import RuntimeManifest

__all__ = ["RuntimeManifest"]
