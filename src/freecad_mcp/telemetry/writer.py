"""Thread-safe one-file-per-process JSONL telemetry writer."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterable, Mapping
from datetime import UTC
from pathlib import Path
from typing import Any

from .context import get_context
from .events import build_event
from .redaction import redact_payload

logger = logging.getLogger("FreeCADMCPserver.telemetry")


def telemetry_enabled() -> bool:
    return os.environ.get("FREECAD_MCP_TELEMETRY", "1") != "0"


def _max_file_bytes() -> int:
    raw = os.environ.get("FREECAD_MCP_TELEMETRY_MAX_BYTES", str(8 * 1024 * 1024))
    try:
        return max(4096, int(raw))
    except ValueError:
        return 8 * 1024 * 1024


def _backup_count() -> int:
    raw = os.environ.get("FREECAD_MCP_TELEMETRY_BACKUPS", "3")
    try:
        return min(10, max(1, int(raw)))
    except ValueError:
        return 3


def _default_path() -> Path:
    explicit = os.environ.get("FREECAD_MCP_TELEMETRY_FILE")
    if explicit:
        return Path(explicit)
    directory = Path(
        os.environ.get("FREECAD_MCP_DEBUG_LOG_DIR")
        or os.environ.get("FREECAD_MCP_TELEMETRY_DIR")
        or "debug_logs"
    )
    context = get_context()
    from datetime import datetime

    date = datetime.now(UTC).strftime("%Y-%m-%d")
    short_session = context.session_id.replace("-", "")[:12]
    return directory / f"mcp_debug_{date}_{os.getpid()}_{short_session}.jsonl"


class TelemetryWriter:
    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else _default_path()
        self.enabled = telemetry_enabled() if enabled is None else bool(enabled)
        self._sequence = 0
        self._lock = threading.RLock()
        self._closed = False

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    def _rotate_locked(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < _max_file_bytes():
            return
        count = _backup_count()
        oldest = self.path.with_name(f"{self.path.name}.{count}")
        if oldest.exists():
            oldest.unlink()
        for index in range(count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def emit(
        self,
        source: str,
        event: str,
        *,
        status: str = "succeeded",
        duration_ms: float | None = None,
        error_code: str | None = None,
        payload: Mapping[str, Any] | None = None,
        secrets: Iterable[str] = (),
    ) -> dict[str, Any] | None:
        if not self.enabled or self._closed:
            return None
        with self._lock:
            self._sequence += 1
            safe_payload = redact_payload(payload or {}, secrets=secrets)
            entry = build_event(
                sequence=self._sequence,
                source=source,
                event=event,
                status=status,
                duration_ms=duration_ms,
                error_code=error_code,
                payload=safe_payload if isinstance(safe_payload, Mapping) else {
                    "value": safe_payload
                },
            )
            line = json.dumps(
                entry,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                default=str,
            ) + "\n"
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate_locked()
                with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(line)
                    handle.flush()
            except OSError as exc:
                logger.warning("Failed to write MCP telemetry: %s", exc)
                return None
            return entry

    def close(self) -> None:
        with self._lock:
            self._closed = True


_DEFAULT_WRITER: TelemetryWriter | None = None
_DEFAULT_LOCK = threading.Lock()


def get_default_writer() -> TelemetryWriter:
    global _DEFAULT_WRITER
    with _DEFAULT_LOCK:
        if _DEFAULT_WRITER is None or _DEFAULT_WRITER._closed:
            _DEFAULT_WRITER = TelemetryWriter()
        return _DEFAULT_WRITER


def emit_event(
    source: str,
    event: str,
    *,
    status: str = "succeeded",
    duration_ms: float | None = None,
    error_code: str | None = None,
    payload: Mapping[str, Any] | None = None,
    secrets: Iterable[str] = (),
) -> dict[str, Any] | None:
    return get_default_writer().emit(
        source,
        event,
        status=status,
        duration_ms=duration_ms,
        error_code=error_code,
        payload=payload,
        secrets=secrets,
    )


def close_default_writer() -> None:
    global _DEFAULT_WRITER
    with _DEFAULT_LOCK:
        if _DEFAULT_WRITER is not None:
            _DEFAULT_WRITER.close()


__all__ = [
    "TelemetryWriter",
    "close_default_writer",
    "emit_event",
    "get_default_writer",
    "telemetry_enabled",
]
