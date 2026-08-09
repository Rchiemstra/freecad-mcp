"""Load bootstrapped subject manifests."""

from __future__ import annotations

from functools import cache

from .schema import SubjectManifest
from .subject_manifest_index import SUBJECT_MANIFESTS


@cache
def all_subject_manifests() -> tuple[SubjectManifest, ...]:
    return SUBJECT_MANIFESTS


__all__ = ["all_subject_manifests"]
