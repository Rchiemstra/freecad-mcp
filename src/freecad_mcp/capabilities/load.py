"""Load bootstrapped subject manifests."""

from __future__ import annotations

import importlib
from functools import cache
from pathlib import Path

from .schema import SubjectManifest

_PACKAGE_ROOT = Path(__file__).resolve().parent
_SKIP_NAMES = frozenset(
    {
        "__pycache__",
        "generated",
    }
)


@cache
def all_subject_manifests() -> tuple[SubjectManifest, ...]:
    manifests: list[SubjectManifest] = []
    for child in sorted(_PACKAGE_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name in _SKIP_NAMES:
            continue
        manifest_path = child / "manifest.py"
        if not manifest_path.exists():
            continue
        module = importlib.import_module(
            f"freecad_mcp.capabilities.{child.name}.manifest"
        )
        manifest = getattr(module, "MANIFEST")
        if not isinstance(manifest, SubjectManifest):
            raise TypeError(f"{module.__name__}.MANIFEST must be SubjectManifest")
        manifests.append(manifest)
    return tuple(manifests)


__all__ = ["all_subject_manifests"]
