"""Extracted ``RuntimeManifest`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
    SUPPORTED_FEATURES,
)
from .rpc_auth_error import RpcAuthError
from .validation import (
    _format_utc,
    _normalize_features,
    _parse_utc,
    _require_exact_keys,
    _require_host,
    _require_identifier,
    _require_pid,
    _require_port,
    _require_sequence,
    _require_string,
    _require_uuid,
)


@dataclass(frozen=True)
class RuntimeManifest:
    profile_id: str
    addon_runtime_id: str
    freecad_pid: int
    freecad_process_started_at: str
    boot_id: str
    rpc_host: str
    rpc_port: int
    freecad_version: str
    freecad_revision: str
    addon_version: str
    addon_build_id: str
    profile_path_fingerprint: str
    protocol_version: int = PROTOCOL_VERSION
    features: tuple[str, ...] = field(default_factory=lambda: SUPPORTED_FEATURES)

    def __post_init__(self) -> None:
        _require_identifier(self.profile_id, "profile_id")
        object.__setattr__(
            self,
            "addon_runtime_id",
            _require_uuid(self.addon_runtime_id, "addon_runtime_id"),
        )
        _require_pid(self.freecad_pid, "freecad_pid")
        object.__setattr__(
            self,
            "freecad_process_started_at",
            _format_utc(
                _parse_utc(
                    self.freecad_process_started_at, "freecad_process_started_at"
                )
            ),
        )
        _require_identifier(self.boot_id, "boot_id")
        _require_host(self.rpc_host)
        _require_port(self.rpc_port)
        for name in (
            "freecad_version",
            "freecad_revision",
            "addon_version",
            "addon_build_id",
        ):
            _require_string(getattr(self, name), name, maximum=256)
        _require_identifier(self.profile_path_fingerprint, "profile_path_fingerprint")
        if self.protocol_version != PROTOCOL_VERSION:
            raise RpcAuthError(
                "UNSUPPORTED_PROTOCOL",
                "Runtime manifest protocol version is unsupported",
            )
        features = _normalize_features(self.features, "features")
        if not REQUIRED_PROTOCOL_FEATURES.issubset(features):
            raise RpcAuthError(
                "MISSING_PROTOCOL_FEATURE",
                "Runtime manifest omits a required protocol feature",
            )
        object.__setattr__(self, "features", tuple(sorted(features)))

    @property
    def endpoint(self) -> str:
        host = f"[{self.rpc_host}]" if ":" in self.rpc_host else self.rpc_host
        return f"{host}:{self.rpc_port}"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeManifest:
        if not isinstance(payload, Mapping):
            raise RpcAuthError(
                "MALFORMED_MANIFEST", "Runtime manifest must be an object"
            )
        _require_exact_keys(
            payload,
            required={
                "protocol_name",
                "protocol_version",
                "features",
                "profile_id",
                "addon_runtime_id",
                "freecad_pid",
                "freecad_process_started_at",
                "boot_id",
                "rpc_host",
                "rpc_port",
                "endpoint",
                "freecad_version",
                "freecad_revision",
                "addon_version",
                "addon_build_id",
                "profile_path_fingerprint",
            },
            context="runtime manifest",
        )
        if payload["protocol_name"] != PROTOCOL_NAME:
            raise RpcAuthError(
                "UNSUPPORTED_PROTOCOL", "Runtime manifest protocol name is unsupported"
            )
        manifest = cls(
            protocol_version=payload["protocol_version"],
            features=tuple(_require_sequence(payload["features"], "features")),
            profile_id=payload["profile_id"],
            addon_runtime_id=payload["addon_runtime_id"],
            freecad_pid=payload["freecad_pid"],
            freecad_process_started_at=payload["freecad_process_started_at"],
            boot_id=payload["boot_id"],
            rpc_host=payload["rpc_host"],
            rpc_port=payload["rpc_port"],
            freecad_version=payload["freecad_version"],
            freecad_revision=payload["freecad_revision"],
            addon_version=payload["addon_version"],
            addon_build_id=payload["addon_build_id"],
            profile_path_fingerprint=payload["profile_path_fingerprint"],
        )
        if payload["endpoint"] != manifest.endpoint:
            raise RpcAuthError(
                "INSTANCE_MISMATCH", "Runtime manifest endpoint is inconsistent"
            )
        return manifest


RuntimeManifest.__module__ = "freecad_mcp.rpc_auth"
