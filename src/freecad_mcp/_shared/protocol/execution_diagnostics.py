"""Bound and scrub execution diagnostics before public transport or logging."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any

from .redaction import _key_is_sensitive

MAX_DIAGNOSTIC_STRING = 2048
MAX_DIAGNOSTIC_BYTES = 16384


def _secret_key(key: object) -> bool:
    name = str(key).lower().replace('-', '_')
    return _key_is_sensitive(key) or name in {'api_key', 'access_key', 'private_key'} or name.endswith(
        ('_api_key', '_access_key', '_private_key')
    )


def execution_diagnostics(value: Any) -> Any:
    """Preserve JSON field types, redact known credential values and omit source.

    Limits apply to encoded JSON (including escaping), nesting and collection
    sizes. Collect credential values before truncation so a long secret cannot
    leave a recognizable prefix elsewhere in the payload.
    """
    secrets = {value for key, value in os.environ.items() if value and _secret_key(key)}

    sources: set[str] = set()

    def source_field(key: object, parent: Mapping) -> bool:
        return str(key) in {"source", "source_code", "line_code"} or (
            str(key) == "code" and ("file" in parent or "line" in parent
                or re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", str(parent[key])) is None)
        )

    def collect(item: Any, depth: int = 0, sensitive: bool = False) -> None:
        if depth > 16:
            return
        if isinstance(item, str):
            if sensitive and item:
                secrets.add(item)
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if isinstance(child, str) and child and source_field(key, item):
                    sources.add(child)
                collect(child, depth + 1, sensitive or _secret_key(key))
        elif isinstance(item, (list, tuple)):
            for child in item:
                collect(child, depth + 1, sensitive)

    collect(value)
    ordered = sorted(secrets, key=len, reverse=True)

    def clean(text: str, limit: int, *, omit_source: bool = True) -> str:
        for secret in ordered:
            text = text.replace(secret, '<redacted>')
        if omit_source:
            for source in sorted(sources, key=len, reverse=True):
                text = text.replace(source, '<source omitted>')
        # ensure_ascii=True costs at most 12 bytes per Unicode character.
        return text.encode('utf-8', errors='replace')[:limit].decode('utf-8', errors='ignore')

    def visit(item: Any, depth: int, width: int, limit: int) -> Any:
        if isinstance(item, str):
            return clean(item, limit)
        if isinstance(item, Mapping):
            if depth > 8:
                return {}
            result = {}
            # Keep the semantic code even when the diagnostic map is truncated.
            keys = sorted(item, key=lambda key: str(key) != 'error_code')
            if depth == 0:
                required = {'code', 'message', 'data', 'error_code'}
                keys = ([key for key in keys if str(key) in required]
                        + [key for key in keys if str(key) not in required][:width])
            else:
                keys = keys[:width]
            for key in keys:
                name = clean(str(key), min(limit, 128), omit_source=False)
                child = item[key]
                if _secret_key(key):
                    result[name] = '<redacted>'
                elif isinstance(child, str) and source_field(key, item):
                    result[name] = ''  # source is never public diagnostic text
                elif str(key) == 'traceback' and isinstance(child, str):
                    # Formatted Python tracebacks contain source and caret lines.
                    # Structured frames retain file/function/line information.
                    result[name] = ''
                elif isinstance(child, str) and str(key) in {
                    'file', 'function', 'exception_type', 'type', 'error_code'
                }:
                    result[name] = clean(child, max(limit, 128), omit_source=False)
                else:
                    result[name] = visit(child, depth + 1, width, limit)
            return result
        if isinstance(item, (list, tuple)):
            return [] if depth > 8 else [visit(child, depth + 1, width, limit) for child in item[:width]]
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return clean(type(item).__name__, limit)

    width, limit = 32, MAX_DIAGNOSTIC_STRING
    while True:
        result = visit(value, 0, width, limit)
        if len(json.dumps(result, ensure_ascii=True).encode('utf-8')) <= MAX_DIAGNOSTIC_BYTES:
            return result
        width = max(1, width // 2)
        limit = max(16, limit // 2)
