"""Primary execute_code AST analysis entry point."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Mapping
from typing import Any

from .collect_features import collect_ast_features


def analyze_execute_code(
    code: str, options: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Return bounded features and hashes, never source text."""

    raw = str(code).encode("utf-8", errors="replace")
    result: dict[str, Any] = {
        "code_sha256": hashlib.sha256(raw).hexdigest(),
        "code_bytes": len(raw),
        "read_only": bool((options or {}).get("read_only")),
        "execution_mode": str((options or {}).get("execution_mode") or "auto"),
        "document_scope": sorted(
            {
                str(item)
                for item in (
                    (options or {}).get("document"),
                    *((options or {}).get("affected_documents") or ()),
                )
                if item
            }
        ),
        "imports": [],
        "call_families": [],
        "typed_tool_suggestions": [],
        "ast_pattern_hash": None,
        "parse_error": None,
    }
    try:
        tree = ast.parse(str(code), mode="exec")
    except (SyntaxError, ValueError) as exc:
        result["parse_error"] = type(exc).__name__
        return result

    imports, calls, suggestions = collect_ast_features(tree)
    pattern = ast.dump(tree, annotate_fields=False, include_attributes=False)
    result.update(
        imports=sorted(imports),
        call_families=sorted(calls)[:128],
        typed_tool_suggestions=sorted(suggestions),
        ast_pattern_hash=hashlib.sha256(pattern.encode("utf-8")).hexdigest(),
    )
    return result
