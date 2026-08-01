"""Runtime manifest construction for authenticated RPC v2."""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence

from ..lease_protocol_types.constants import (
    _PROCESS_STARTED_AT,
    SUPPORTED_FEATURES,
)
from ..lease_protocol_types.runtime_manifest import RuntimeManifest
from ..lease_protocol_types.validation import _format_utc


def make_runtime_manifest(
    *,
    profile_id: str,
    addon_runtime_id: str | None = None,
    freecad_pid: int | None = None,
    freecad_process_started_at: str | None = None,
    boot_id: str,
    rpc_host: str,
    rpc_port: int,
    freecad_version: str,
    freecad_revision: str,
    addon_version: str,
    addon_build_id: str,
    profile_path_fingerprint: str,
    features: Sequence[str] = SUPPORTED_FEATURES,
) -> RuntimeManifest:
    """Construct a validated manifest, supplying safe runtime defaults."""

    return RuntimeManifest(
        profile_id=profile_id,
        addon_runtime_id=addon_runtime_id or str(uuid.uuid4()),
        freecad_pid=os.getpid() if freecad_pid is None else freecad_pid,
        freecad_process_started_at=freecad_process_started_at
        or _format_utc(_PROCESS_STARTED_AT),
        boot_id=boot_id,
        rpc_host=rpc_host,
        rpc_port=rpc_port,
        freecad_version=freecad_version,
        freecad_revision=freecad_revision,
        addon_version=addon_version,
        addon_build_id=addon_build_id,
        profile_path_fingerprint=profile_path_fingerprint,
        features=tuple(features),
    )
