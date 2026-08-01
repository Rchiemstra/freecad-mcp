from __future__ import annotations

import os
from typing import Any


def _legacy_alias(kind: str, value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if kind == "path":
        raw = os.path.normcase(os.path.realpath(os.path.abspath(raw)))
    return f"{kind}:{raw}"

def legacy_selector_doc_key(
    selector: dict[str, Any],
    legacy_document_keys: dict[str, str],
) -> str:
    """Resolve a typed selector to one legacy key, requiring all fields agree."""

    aliases = (
        _legacy_alias("name", selector.get("document_name")),
        _legacy_alias("session", selector.get("document_session_uuid")),
        _legacy_alias("path", selector.get("canonical_path")),
    )
    supplied = tuple(alias for alias in aliases if alias)
    if not supplied or any(
        alias not in legacy_document_keys for alias in supplied
    ):
        return ""
    resolved = {
        legacy_document_keys[alias]
        for alias in supplied
    }
    if len(resolved) > 1:
        return ""
    return next(iter(resolved), "")

def forget_legacy_document_key(
    doc_key: str,
    legacy_document_keys: dict[str, str] | None,
) -> None:
    if legacy_document_keys is None:
        return
    for alias, candidate in list(legacy_document_keys.items()):
        if candidate == doc_key:
            legacy_document_keys.pop(alias, None)
