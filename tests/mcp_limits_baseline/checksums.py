#!/usr/bin/env python3
"""SHA-256 helpers for immutable MCP limits campaign fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_file_sha256(path: Path, expected_hex: str) -> None:
    actual = sha256_hex(path)
    expected = expected_hex.lower()
    if actual != expected:
        raise AssertionError(
            f"checksum mismatch for {path.name}: expected {expected}, got {actual}"
        )
