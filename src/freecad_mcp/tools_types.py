"""Shared MCP tool input types (Phase 7 / 7D)."""

from __future__ import annotations

from types import MappingProxyType

from typing_extensions import TypedDict


class DocumentSelectorInput(TypedDict, total=False):
    """Exact public fields accepted by document lifecycle selectors."""

    __pydantic_config__ = MappingProxyType({"extra": "forbid"})

    document_name: str
    document_session_uuid: str
    canonical_path: str
