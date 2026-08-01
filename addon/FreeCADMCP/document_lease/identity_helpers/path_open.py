"""Reject open paths already owned by a live document."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model import FileIdentity
from .path_availability import assert_path_available
from .path_canonicalize import canonicalize_path
from .path_file_identity import file_identity_for_path

if TYPE_CHECKING:
    from os import PathLike


def assert_open_path_available(
    self: Any, path: str | PathLike[str]
) -> tuple[str, str, FileIdentity | None]:
    """Reject a path/file identity already owned by a live document.

    Typed open calls use this before touching FreeCAD's application
    document list.  Registration still repeats the check after open to
    close the unavoidable filesystem-to-GUI race conservatively.
    """

    canonical, comparison = canonicalize_path(path, platform=self.platform)
    file_identity = file_identity_for_path(canonical, platform=self.platform)
    with self._lock:
        assert_path_available(self, comparison, file_identity)
    return canonical, comparison, file_identity
