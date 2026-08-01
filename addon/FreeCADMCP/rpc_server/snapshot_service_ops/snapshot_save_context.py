"""Snapshot save authorization and observer attribution."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any


def snapshot_save_capability(
    documents: list[Any],
    mutation_generations: Mapping[str, int] | None,
):
    """Authorize only the internal ``saveCopy`` calls used by worker snapshots."""

    if mutation_generations is None:
        return nullcontext([])
    try:
        from addon.FreeCADMCP.document_lease import core_authority
    except ImportError:
        try:
            from document_lease import core_authority
        except ImportError:
            return nullcontext([])
    return core_authority.open_documents_mutation_capability(
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

    document_lock = None
    marker_entered = False
    try:
        if mutation_generations:
            if not mutation_request_id or not mutation_document_keys:
                raise RuntimeError("leased snapshot mutation attribution is unavailable")
            try:
                from addon.FreeCADMCP import document_lock
            except ImportError:
                import document_lock
            marker_entered = True
            if not document_lock.begin_agent_mutation_scope(
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
        if marker_entered and document_lock is not None:
            document_lock.end_agent_mutation_scope(
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
    try:
        from addon.FreeCADMCP import document_lock
    except ImportError:
        import document_lock
    entered = document_lock.begin_internal_snapshot_save_scope(
        request_id,
        document,
        target_path,
    )
    if not entered:
        document_lock.end_internal_snapshot_save_scope(
            request_id,
            document,
            target_path,
        )
        raise RuntimeError("internal snapshot save attribution was rejected")
    try:
        yield
    finally:
        document_lock.end_internal_snapshot_save_scope(
            request_id,
            document,
            target_path,
        )
