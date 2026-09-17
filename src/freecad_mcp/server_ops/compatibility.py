"""Compatibility (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from typing import Any

from .._shared.protocol.constants import REQUIRED_PROTOCOL_FEATURES
from ..build_info import build_id, package_version, protocol_version

_UNAUTHENTICATED_WARNING = "Authenticated runtime identity is not available"


def normalize_protocol_versions(values: Any) -> list[int]:
    if not values:
        return []
    try:
        return sorted({int(item) for item in values})
    except (TypeError, ValueError):
        return []


def protocol_mismatch_warning(addon_protocol: int) -> str:
    return f"RPC protocol mismatch: MCP={protocol_version}, addon={addon_protocol}"


def compatibility_for_manifest(manifest: Any | None) -> dict[str, Any]:
    warnings: list[str] = []
    if manifest is None:
        return {
            "compatible": True,
            "warnings": [_UNAUTHENTICATED_WARNING],
        }
    addon_protocol = int(getattr(manifest, "protocol_version", 0) or 0)
    features = set(getattr(manifest, "features", ()) or ())
    missing = sorted(set(REQUIRED_PROTOCOL_FEATURES).difference(features))
    compatible = addon_protocol == protocol_version and not missing
    addon_build = str(getattr(manifest, "addon_build_id", "") or "")
    if addon_build and addon_build != build_id:
        warnings.append(
            "MCP package and FreeCAD addon build IDs differ; protocol compatibility "
            "permits this connection"
        )
    addon_version = str(getattr(manifest, "addon_version", "") or "")
    if addon_version and addon_version != package_version:
        warnings.append(
            "MCP package and FreeCAD addon versions differ; verify both were "
            "installed from the intended checkout"
        )
    if addon_protocol != protocol_version:
        warnings.append(protocol_mismatch_warning(addon_protocol))
    if missing:
        warnings.append("Missing required RPC features: " + ", ".join(missing))
    return {"compatible": compatible, "warnings": warnings}


def compatibility_for_unauthenticated(instance_info: dict[str, Any]) -> dict[str, Any]:
    """Assess protocol support before an authenticated handshake is available."""

    supported = normalize_protocol_versions(instance_info.get("protocol_versions"))
    active_raw = instance_info.get("protocol_version")
    active = int(active_raw) if active_raw is not None else None

    if protocol_version in supported:
        return {
            "compatible": False,
            "warnings": [_UNAUTHENTICATED_WARNING],
        }

    mismatch_protocol = active if active is not None else (supported[0] if supported else 1)
    return {
        "compatible": False,
        "warnings": [protocol_mismatch_warning(mismatch_protocol)],
    }


def runtime_compatibility(
    manifest: Any | None,
    instance_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if manifest is not None:
        return compatibility_for_manifest(manifest)
    return compatibility_for_unauthenticated(instance_info or {})
