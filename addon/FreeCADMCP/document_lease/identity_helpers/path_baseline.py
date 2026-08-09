"""Stable file baseline capture for lease dirty detection."""

from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

from ..identity_types.document_identity_error import DocumentIdentityError
from ..model import FileBaseline
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path

if TYPE_CHECKING:
    from os import PathLike


def capture_file_baseline(
    path: str | PathLike[str],
    *,
    platform: str | None = None,
    chunk_size: int = 1024 * 1024,
) -> FileBaseline:
    """Hash an unchanged file, rejecting a concurrent writer."""

    canonical, _ = canonicalize_path(path, platform=platform)
    before = os.stat(canonical)
    digest = hashlib.sha256()
    with open(canonical, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    after = os.stat(canonical)
    before_key = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_key = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_key != after_key:
        raise DocumentIdentityError("document changed while its baseline was captured")
    return FileBaseline(
        mtime_ns=int(after.st_mtime_ns),
        size=int(after.st_size),
        sha256=digest.hexdigest(),
        file_identity=file_identity_for_path(canonical, platform=platform),
    )
