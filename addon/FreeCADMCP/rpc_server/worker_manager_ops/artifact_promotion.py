"""Promote worker artifacts from staging into the manager artifact root."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def promote_artifacts(
    manager,
    artifacts: Any,
    staging: Path,
    job_id: str,
) -> list[dict[str, Any]]:
    from ..worker_manager import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS_TOTAL_BYTES
    from ..worker_protocol_types.protocol_error import ProtocolError

    if not isinstance(artifacts, list):
        raise ProtocolError("worker artifacts must be a list")
    staging = staging.resolve()
    destination = (manager.artifact_root / job_id).resolve()
    total = 0
    promoted = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ProtocolError("worker artifact entry must be an object")
        source = Path(item.get("path", "")).resolve()
        if staging not in source.parents or not source.is_file():
            raise ProtocolError("worker artifact escaped its staging directory")
        size = source.stat().st_size
        if size > MAX_ARTIFACT_BYTES:
            raise ProtocolError("individual artifact exceeds 256 MiB")
        total += size
        if total > MAX_ARTIFACTS_TOTAL_BYTES:
            raise ProtocolError("job artifacts exceed 512 MiB total")
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        os.replace(source, target)
        promoted.append({
            "artifact_id": f"{job_id}:{index}",
            "name": item.get("name", source.stem),
            "format": item.get("format", source.suffix.lstrip(".")),
            "path": str(target),
            "size_bytes": size,
            "expires_in_seconds": 3600,
        })
    return promoted
