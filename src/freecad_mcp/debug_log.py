"""Bounded, redacted MCP debug logging (R1).

Debug logging is opt-in via ``FREECAD_MCP_DEBUG=1``. By default only metadata
(hashes, byte counts, tool names, timing, status) is written — never full code
bodies or base64 image payloads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("FreeCADMCPserver.debug")

_DEFAULT_LOG_PATH = Path(os.environ.get("FREECAD_MCP_DEBUG_LOG", "mcp_debug.log"))
_REDACT_CODE = os.environ.get("FREECAD_MCP_DEBUG_REDACT_CODE", "1") != "0"
_REDACT_IMAGES = os.environ.get("FREECAD_MCP_DEBUG_REDACT_IMAGES", "1") != "0"

_BASE64_RE = re.compile(r'"data"\s*:\s*"[A-Za-z0-9+/=\s]{200,}"')
_CODE_FIELD_RE = re.compile(r'("code"\s*:\s*")([^"]*)(")', re.DOTALL)
_IMAGE_MIME_RE = re.compile(
    r'("mimeType"\s*:\s*"image/[^"]+"\s*,\s*"data"\s*:\s*")([^"]*)(")',
    re.DOTALL,
)


def debug_enabled() -> bool:
    return os.environ.get("FREECAD_MCP_DEBUG", "0") == "1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def redact_payload(payload: Any) -> Any:
    """Return a log-safe copy of *payload* with code and image bodies redacted."""
    if payload is None:
        return None
    try:
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        text = str(payload)

    original_len = len(text)
    redacted = text

    if _REDACT_CODE:
        def _code_sub(m: re.Match[str]) -> str:
            body = m.group(2)
            return f'{m.group(1)}<redacted code sha256={_sha256(body)} len={len(body)}>{m.group(3)}'

        redacted = _CODE_FIELD_RE.sub(_code_sub, redacted)

    if _REDACT_IMAGES:
        def _img_sub(m: re.Match[str]) -> str:
            body = m.group(2)
            return f'{m.group(1)}<redacted image sha256={_sha256(body)} len={len(body)}>{m.group(3)}'

        redacted = _IMAGE_MIME_RE.sub(_img_sub, redacted)
        redacted = _BASE64_RE.sub(
            lambda m: m.group(0).split('"data"')[0]
            + '"data":"<redacted base64>"',
            redacted,
        )

    try:
        return json.loads(redacted)
    except Exception:
        if len(redacted) > 4096:
            return {
                "redacted": True,
                "sha256": _sha256(text),
                "bytes": original_len,
                "preview": redacted[:512] + "…",
            }
        return redacted


def _max_log_bytes() -> int:
    return int(os.environ.get("FREECAD_MCP_DEBUG_MAX_BYTES", str(512 * 1024)))


def _rotate_if_needed(path: Path) -> None:
    try:
        max_bytes = _max_log_bytes()
        if path.exists() and path.stat().st_size >= max_bytes:
            backup = path.parent / (path.name + ".1")
            if backup.exists():
                backup.unlink()
            path.replace(backup)
    except OSError as exc:
        logger.warning("Failed to rotate debug log %s: %s", path, exc)


def log_event(
    direction: str,
    *,
    method: str | None = None,
    tool: str | None = None,
    payload: Any = None,
    status: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    path: Path | None = None,
) -> None:
    if not debug_enabled():
        return
    log_path = path or _DEFAULT_LOG_PATH
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "direction": direction,
    }
    if method:
        entry["method"] = method
    if tool:
        entry["tool"] = tool
    if status:
        entry["status"] = status
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    if error:
        entry["error"] = error
    if payload is not None:
        safe = redact_payload(payload)
        raw = json.dumps(safe, ensure_ascii=False, default=str)
        entry["payload_sha256"] = _sha256(raw)
        entry["payload_bytes"] = len(raw)
        entry["payload"] = safe

    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(log_path)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError as exc:
        logger.warning("Failed to write debug log: %s", exc)
