"""Normalized FreeCAD build identity for worker admission."""

from __future__ import annotations

from dataclasses import dataclass

from .worker_version_mismatch import WorkerVersionMismatch


@dataclass(frozen=True)
class BuildIdentity:
    version: tuple[int, int, int]
    revision: str | None


def normalize_build_identity(values: tuple[str, str, str, str]) -> BuildIdentity:
    if len(values) != 4 or any(not str(value).strip() for value in values[:3]):
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD version identity")
    try:
        version = tuple(int(str(value).strip()) for value in values[:3])
    except ValueError as exc:
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD version identity") from exc
    raw_revision = str(values[3]).strip()
    if raw_revision.lower() in {"unknown", "none", "n/a", "ambiguous"}:
        raise WorkerVersionMismatch("missing or ambiguous FreeCAD revision identity")
    revision = raw_revision or None
    return BuildIdentity(version=version, revision=revision)  # type: ignore[arg-type]


def require_compatible_builds(
    gui_values: tuple[str, str, str, str],
    worker_values: tuple[str, str, str, str],
) -> None:
    gui = normalize_build_identity(gui_values)
    worker = normalize_build_identity(worker_values)
    if (gui.revision is None) != (worker.revision is None):
        raise WorkerVersionMismatch(
            f"development/release mismatch: GUI {gui}, worker {worker}"
        )
    if gui.revision is not None:
        if gui.version != worker.version or gui.revision != worker.revision:
            raise WorkerVersionMismatch(
                f"revision identity mismatch: GUI {gui}, worker {worker}"
            )
    elif gui.version != worker.version:
        raise WorkerVersionMismatch(
            f"stable release mismatch: GUI {gui.version}, worker {worker.version}"
        )
