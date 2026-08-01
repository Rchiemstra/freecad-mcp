"""Compatibility (Phase 7 / 7D server_ops)."""

from __future__ import annotations

from typing import Any

from ..build_info import build_id, package_version, protocol_version
from ..rpc_auth import REQUIRED_PROTOCOL_FEATURES


def compatibility_for_manifest(manifest: Any | None) -> dict[str, Any]:
    warnings: list[str] = []
    if manifest is None:
        return {
            "compatible": True,
            "warnings": ["Authenticated runtime identity is not available"],
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
        warnings.append(
            f"RPC protocol mismatch: MCP={protocol_version}, addon={addon_protocol}"
        )
    if missing:
        warnings.append("Missing required RPC features: " + ", ".join(missing))
    return {"compatible": compatible, "warnings": warnings}
