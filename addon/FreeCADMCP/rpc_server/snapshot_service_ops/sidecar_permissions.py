"""Sidecar permission helpers (monkeypatch surface lives on ``snapshot_service``)."""

from __future__ import annotations

from typing import Any


def harden_directory_permissions(path: Any, *, strict: bool) -> None:
    from ..snapshot_service import _harden_directory_permissions

    _harden_directory_permissions(path, strict=strict)


def harden_permissions(path: Any, *, strict: bool) -> None:
    from ..snapshot_service import _harden_permissions

    _harden_permissions(path, strict=strict)
