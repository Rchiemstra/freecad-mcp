"""Document path canonicalization for lease aliases."""

from __future__ import annotations

import os


def canonicalize_document_path(path: str | os.PathLike[str]) -> str:
    """Return the platform comparison key for a document path.

    ``realpath`` is intentionally used even when the final file does not exist:
    it still resolves the existing parent and gives Save As aliases the same
    normalization rules as an already-saved document.
    """

    value = os.fspath(path).strip()
    if not value:
        raise ValueError("document path must not be empty")
    absolute = os.path.abspath(os.path.normpath(value))
    return os.path.normcase(os.path.realpath(absolute))
