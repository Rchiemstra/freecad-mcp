"""Extracted ``InstanceManifest`` for ARCH002 (workstream 1G)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    INSTANCE_MANIFEST_SCHEMA_VERSION,
    PROTOCOL_VERSION,
    REQUIRED_PROTOCOL_FEATURES,
)
from .profile_secret import load_profile_secret
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
    _require_string,
    _require_uuid,
)


def _validate_instance_manifest_required(manifest: InstanceManifest) -> None:
    if manifest.schema_version != INSTANCE_MANIFEST_SCHEMA_VERSION:
        raise RpcAuthError(
            "UNSUPPORTED_INSTANCE_MANIFEST",
            "Instance manifest schema is unsupported",
        )
    _require_host(manifest.rpc_host)
    _require_port(manifest.rpc_port)
    _require_identifier(manifest.profile_instance_id, "profile_instance_id")
    _require_string(manifest.profile_path, "profile_path", maximum=4096)
    _require_string(manifest.auth_secret_file, "auth_secret_file", maximum=4096)
    _format_utc(_parse_utc(manifest.created_at, "created_at"))


def _normalize_instance_manifest_runtime_fields(manifest: InstanceManifest) -> None:
    if manifest.expected_freecad_pid is not None:
        _require_pid(manifest.expected_freecad_pid, "expected_freecad_pid")
    if manifest.expected_freecad_process_started_at is not None:
        object.__setattr__(
            manifest,
            "expected_freecad_process_started_at",
            _format_utc(
                _parse_utc(
                    manifest.expected_freecad_process_started_at,
                    "expected_freecad_process_started_at",
                )
            ),
        )
    if manifest.expected_addon_runtime_id is not None:
        object.__setattr__(
            manifest,
            "expected_addon_runtime_id",
            _require_uuid(
                manifest.expected_addon_runtime_id, "expected_addon_runtime_id"
            ),
        )
    if manifest.expected_boot_id is not None:
        _require_identifier(manifest.expected_boot_id, "expected_boot_id")
    if (
        manifest.expected_protocol_version is not None
        and manifest.expected_protocol_version != PROTOCOL_VERSION
    ):
        raise RpcAuthError(
            "UNSUPPORTED_PROTOCOL",
            "Instance manifest protocol version is unsupported",
        )
    if manifest.expected_protocol_features is not None:
        features = _normalize_features(
            manifest.expected_protocol_features, "expected_protocol_features"
        )
        if not REQUIRED_PROTOCOL_FEATURES.issubset(features):
            raise RpcAuthError(
                "MISSING_PROTOCOL_FEATURE",
                "Instance manifest omits a required protocol feature",
            )
        object.__setattr__(
            manifest, "expected_protocol_features", tuple(sorted(features))
        )


def _normalize_instance_manifest_build_fields(manifest: InstanceManifest) -> None:
    if manifest.expected_addon_version is not None:
        _require_string(
            manifest.expected_addon_version, "expected_addon_version", maximum=256
        )
    if manifest.expected_addon_build_id is not None:
        _require_identifier(manifest.expected_addon_build_id, "expected_addon_build_id")
    if manifest.expected_freecad_version is not None:
        _require_string(
            manifest.expected_freecad_version, "expected_freecad_version", maximum=256
        )
    if manifest.expected_freecad_revision is not None:
        _require_string(
            manifest.expected_freecad_revision,
            "expected_freecad_revision",
            maximum=256,
        )
    if manifest.expected_profile_path_fingerprint is not None:
        _require_identifier(
            manifest.expected_profile_path_fingerprint,
            "expected_profile_path_fingerprint",
        )


@dataclass(frozen=True)
class InstanceManifest:
    """Persistent isolated-profile manifest plus optional launched-runtime facts."""

    rpc_host: str
    rpc_port: int
    profile_instance_id: str
    profile_path: str
    auth_secret_file: str = field(repr=False)
    expected_freecad_pid: int | None = None
    expected_freecad_process_started_at: str | None = None
    expected_addon_runtime_id: str | None = None
    expected_boot_id: str | None = None
    expected_protocol_version: int | None = None
    expected_protocol_features: tuple[str, ...] | None = None
    expected_addon_version: str | None = None
    expected_addon_build_id: str | None = None
    expected_freecad_version: str | None = None
    expected_freecad_revision: str | None = None
    expected_profile_path_fingerprint: str | None = None
    created_at: str = ""
    schema_version: int = INSTANCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_instance_manifest_required(self)
        _normalize_instance_manifest_runtime_fields(self)
        _normalize_instance_manifest_build_fields(self)

    def require_complete_runtime(self) -> None:
        """Reject a setup-only manifest before any authenticated connection."""

        required = {
            "expected_freecad_pid": self.expected_freecad_pid,
            "expected_freecad_process_started_at": (
                self.expected_freecad_process_started_at
            ),
            "expected_addon_runtime_id": self.expected_addon_runtime_id,
            "expected_boot_id": self.expected_boot_id,
            "expected_protocol_version": self.expected_protocol_version,
            "expected_protocol_features": self.expected_protocol_features,
            "expected_addon_version": self.expected_addon_version,
            "expected_addon_build_id": self.expected_addon_build_id,
            "expected_freecad_version": self.expected_freecad_version,
            "expected_freecad_revision": self.expected_freecad_revision,
            "expected_profile_path_fingerprint": (
                self.expected_profile_path_fingerprint
            ),
        }
        if any(value is None for value in required.values()):
            raise RpcAuthError(
                "INCOMPLETE_INSTANCE_MANIFEST",
                "Instance manifest does not contain an exact launched runtime identity",
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> InstanceManifest:
        if not isinstance(payload, Mapping):
            raise RpcAuthError(
                "MALFORMED_INSTANCE_MANIFEST", "Instance manifest must be an object"
            )
        _require_exact_keys(
            payload,
            required={
                "schema_version",
                "rpc_host",
                "rpc_port",
                "profile_instance_id",
                "profile_path",
                "auth_secret_file",
                "expected_freecad_pid",
                "expected_freecad_process_started_at",
                "expected_addon_runtime_id",
                "expected_boot_id",
                "expected_protocol_version",
                "expected_protocol_features",
                "expected_addon_version",
                "expected_addon_build_id",
                "expected_freecad_version",
                "expected_freecad_revision",
                "expected_profile_path_fingerprint",
                "created_at",
            },
            context="instance manifest",
        )
        return cls(**dict(payload))

    def load_secret(self, *, require_owner_only: bool = True) -> bytes:
        return load_profile_secret(
            self.auth_secret_file, require_owner_only=require_owner_only
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rpc_host": self.rpc_host,
            "rpc_port": self.rpc_port,
            "profile_instance_id": self.profile_instance_id,
            "profile_path": self.profile_path,
            "auth_secret_file": self.auth_secret_file,
            "expected_freecad_pid": self.expected_freecad_pid,
            "expected_freecad_process_started_at": (
                self.expected_freecad_process_started_at
            ),
            "expected_addon_runtime_id": self.expected_addon_runtime_id,
            "expected_boot_id": self.expected_boot_id,
            "expected_protocol_version": self.expected_protocol_version,
            "expected_protocol_features": (
                list(self.expected_protocol_features)
                if self.expected_protocol_features is not None
                else None
            ),
            "expected_addon_version": self.expected_addon_version,
            "expected_addon_build_id": self.expected_addon_build_id,
            "expected_freecad_version": self.expected_freecad_version,
            "expected_freecad_revision": self.expected_freecad_revision,
            "expected_profile_path_fingerprint": (
                self.expected_profile_path_fingerprint
            ),
            "created_at": self.created_at,
        }


InstanceManifest.__module__ = "freecad_mcp.rpc_auth"
