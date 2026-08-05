"""Neutral scopes for read-only worker snapshot copies."""

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


def bind_snapshot_save_context(bindings: SnapshotSaveBindings) -> None:
    """Retain the former binder as a stateless compatibility no-op."""

    del bindings


def snapshot_save_capability(
    documents: list[Any],
    mutation_generations: Mapping[str, int] | None,
):
    """Return a neutral scope; ``saveCopy`` owns no document authority."""

    del documents, mutation_generations
    return nullcontext([])


@contextmanager
def snapshot_save_context(
    documents: list[Any],
    mutation_generations: Mapping[str, int] | None,
    mutation_request_id: str,
    mutation_document_keys: tuple[str, ...],
):
    """Keep the historic context shape without opening an authority scope."""

    del mutation_request_id, mutation_document_keys
    with snapshot_save_capability(documents, mutation_generations) as capabilities:
        yield capabilities


@contextmanager
def internal_snapshot_save_observer_scope(
    document: Any,
    target_path: Path,
    request_id: str,
):
    """Retain the former observer scope as a state-free context manager."""

    del document, target_path, request_id
    yield
