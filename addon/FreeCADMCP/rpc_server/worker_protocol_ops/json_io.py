"""Bounded JSON read/write helpers for worker jobs."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ..worker_protocol_types.protocol_error import ProtocolError
from .constants import MAX_RESULT_BYTES


def write_json_atomic(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ProtocolError("worker result JSON exceeds 8 MiB")
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise


def read_json_limited(path: str | Path, limit: int = MAX_RESULT_BYTES) -> dict[str, Any]:
    target = Path(path)
    size = target.stat().st_size
    if size > limit:
        raise ProtocolError(f"JSON file exceeds {limit} bytes")
    with target.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ProtocolError("JSON protocol payload must be an object")
    return value
