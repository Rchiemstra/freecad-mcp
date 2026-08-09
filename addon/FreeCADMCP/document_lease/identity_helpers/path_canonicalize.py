"""Canonical path normalization and comparison keys."""

from __future__ import annotations

import ntpath
import os
import posixpath
from typing import TYPE_CHECKING

from ..identity_types.document_identity_error import DocumentIdentityError
from .platform import platform_name

if TYPE_CHECKING:
    from os import PathLike


def canonicalize_path(
    path: str | PathLike[str], *, platform: str | None = None
) -> tuple[str, str]:
    """Return a display canonical path and stable comparison key.

    A non-native ``platform`` is supported to make path policy unit-testable on
    either host.  Native paths additionally pass through ``realpath`` so that
    ordinary symlink spellings converge.
    """

    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.strip():
        raise DocumentIdentityError("document path must be a non-empty string")
    target = platform_name(platform)
    if target == "windows":
        canonical = ntpath.normpath(ntpath.abspath(raw))
        if os.name == "nt":
            canonical = os.path.realpath(canonical)
        comparison_key = ntpath.normcase(canonical).casefold()
        return canonical, comparison_key

    canonical = posixpath.normpath(posixpath.abspath(raw))
    if os.name != "nt":
        canonical = os.path.realpath(canonical)
    return canonical, canonical
