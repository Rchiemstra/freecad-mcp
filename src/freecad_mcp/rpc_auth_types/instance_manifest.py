"""Compatibility exports for the canonical instance manifest type."""

from __future__ import annotations

from .._shared.protocol.instance_manifest import (
    InstanceManifest,
    _normalize_instance_manifest_build_fields,
    _normalize_instance_manifest_runtime_fields,
    _validate_instance_manifest_required,
)

__all__ = [
    "InstanceManifest",
    "_normalize_instance_manifest_build_fields",
    "_normalize_instance_manifest_runtime_fields",
    "_validate_instance_manifest_required",
]
