"""In-process core mutation-capability context managers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from typing import Any

from .document import resolve_document
from .kinds import LIVE_MUTATION_KINDS
from .owner import is_core_enforced


@contextmanager
def open_mutation_capability(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
) -> Iterator[Any]:
    """Open an in-process core capability for the calling thread."""

    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "openMutationCapability", None)):
        yield None
        return
    if not is_core_enforced(doc):
        yield None
        return
    kind_list = list(kinds) if kinds is not None else list(LIVE_MUTATION_KINDS)
    if not kind_list:
        yield None
        return
    capsule = None
    try:
        capsule = doc.openMutationCapability(kind_list, int(generation))
        yield capsule
    finally:
        # Capsule destructor releases the TLS capability scope.
        del capsule


@contextmanager
def open_documents_mutation_capability(
    documents: Sequence[Any],
    *,
    generations: Mapping[Any, int] | Sequence[int] | int,
    kinds: Sequence[str] | None = None,
) -> Iterator[list[Any]]:
    """Open capabilities for one or more documents; release in reverse order."""

    from contextlib import ExitStack

    docs = [resolve_document(doc) for doc in documents]
    docs = [doc for doc in docs if doc is not None]
    if not docs:
        yield []
        return

    if isinstance(generations, int):
        gen_map = {id(doc): int(generations) for doc in docs}
    elif isinstance(generations, Mapping):
        gen_map = {}
        for doc in docs:
            key = getattr(doc, "Name", doc)
            gen_map[id(doc)] = int(generations.get(key, generations.get(doc, 0)))
    else:
        gen_list = list(generations)
        gen_map = {
            id(doc): int(gen_list[i] if i < len(gen_list) else 0)
            for i, doc in enumerate(docs)
        }

    with ExitStack() as stack:
        capsules: list[Any] = []
        for doc in docs:
            generation = gen_map.get(id(doc), 0)
            capsules.append(
                stack.enter_context(
                    open_mutation_capability(doc, generation=generation, kinds=kinds)
                )
            )
        yield capsules


def capability_context_or_null(
    document: Any,
    *,
    generation: int,
    kinds: Sequence[str] | None = None,
):
    """Return a capability context manager, or nullcontext when unavailable."""

    doc = resolve_document(document)
    if doc is None or not callable(getattr(doc, "openMutationCapability", None)):
        return nullcontext(None)
    return open_mutation_capability(doc, generation=generation, kinds=kinds)
