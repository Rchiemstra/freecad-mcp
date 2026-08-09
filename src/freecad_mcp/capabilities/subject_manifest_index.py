"""Static index of per-subject capability manifests."""

from __future__ import annotations

from .advanced.manifest import MANIFEST as _ADVANCED
from .assembly.manifest import MANIFEST as _ASSEMBLY
from .core.manifest import MANIFEST as _CORE
from .diagnostics.manifest import MANIFEST as _DIAGNOSTICS
from .document_history.manifest import MANIFEST as _DOCUMENT_HISTORY
from .features.manifest import MANIFEST as _FEATURES
from .gear.manifest import MANIFEST as _GEAR
from .gui.manifest import MANIFEST as _GUI
from .io.manifest import MANIFEST as _IO
from .lease.manifest import MANIFEST as _LEASE
from .measure.manifest import MANIFEST as _MEASURE
from .parametric.manifest import MANIFEST as _PARAMETRIC
from .partdesign.manifest import MANIFEST as _PARTDESIGN
from .runtime.manifest import MANIFEST as _RUNTIME
from .schema import SubjectManifest
from .sketch.manifest import MANIFEST as _SKETCH
from .transform.manifest import MANIFEST as _TRANSFORM
from .worker.manifest import MANIFEST as _WORKER

_SUBJECT_MANIFESTS: tuple[SubjectManifest, ...] = (
    _ADVANCED,
    _ASSEMBLY,
    _CORE,
    _DIAGNOSTICS,
    _DOCUMENT_HISTORY,
    _FEATURES,
    _GEAR,
    _GUI,
    _IO,
    _LEASE,
    _MEASURE,
    _PARAMETRIC,
    _PARTDESIGN,
    _RUNTIME,
    _SKETCH,
    _TRANSFORM,
    _WORKER,
)

__all__ = ["SUBJECT_MANIFESTS"]


def subject_manifests() -> tuple[SubjectManifest, ...]:
    return _SUBJECT_MANIFESTS


SUBJECT_MANIFESTS = _SUBJECT_MANIFESTS
