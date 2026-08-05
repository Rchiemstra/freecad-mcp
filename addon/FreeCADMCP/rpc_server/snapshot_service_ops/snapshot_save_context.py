"""Snapshot save authorization and observer attribution."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SnapshotSaveBindings:
    begin_agent_mutation_scope: Any
    end_agent_mutation_scope: Any
    begin_internal_snapshot_save_scope: Any
    end_internal_snapshot_save_scope: Any
    open_documents_mutation_capability: Any


_bindings: SnapshotSaveBindings | None = None


def bind_snapshot_save_context(bindings: SnapshotSaveBindings) -> None:
    if not isinstance(bindings, SnapshotSaveBindings):
        raise TypeError("bindings must be SnapshotSaveBindings")
    global _bindings
    _bindings = bindings


def _require_bindings() -> SnapshotSaveBindings:
    if _bindings is None:
        raise RuntimeError("snapshot save collaborators are not initialized")
    return _bindings


def snapshot_save_capability(
    documents: list[Any],
    mutation_generations: Mapping[str, int] | None,
):
    """Authorize only the internal ``saveCopy`` calls used by worker snapshots."""

    if mutation_generations is None:
        return nullcontext([])
    bindings = _require_bindings()
    return bindings.open_documents_mutation_capability(
        documents,
        generations=mutation_generations,
        kinds=("SaveAs",),
    )


@contextmanager
def snapshot_save_context(
    documents: list[Any],
    mutation_generations: Mapping[str, int] | None,
    mutation_request_id: str,
    mutation_document_keys: tuple[str, ...],
):
    """Keep snapshot saves core-authorized and observer-attributed."""

    marker_entered = False
    bindings = _require_bindings() if mutation_generations else None
    try:
        if mutation_generations:
            if not mutation_request_id or not mutation_document_keys:
                raise RuntimeError("leased snapshot mutation attribution is unavailable")
            marker_entered = True
            if not bindings.begin_agent_mutation_scope(
                mutation_request_id, mutation_document_keys
            ):
                raise RuntimeError(
                    "leased snapshot mutation attribution was rejected"
                )
        with snapshot_save_capability(
            documents, mutation_generations
        ) as capabilities:
            yield capabilities
    finally:
        if marker_entered:
            bindings.end_agent_mutation_scope(
                mutation_request_id, mutation_document_keys
            )


@contextmanager
def internal_snapshot_save_observer_scope(
    document: Any,
    target_path: Path,
    request_id: str,
):
    """Attribute only exact save callbacks from this trusted ``saveCopy``."""

    if not request_id:
        yield
        return
    bindings = _require_bindings()
    entered = bindings.begin_internal_snapshot_save_scope(
        request_id,
        document,
        target_path,
    )
    if not entered:
        bindings.end_internal_snapshot_save_scope(
            request_id,
            document,
            target_path,
        )
        raise RuntimeError("internal snapshot save attribution was rejected")
    try:
        yield
    finally:
        bindings.end_internal_snapshot_save_scope(
            request_id,
            document,
            target_path,
        )
