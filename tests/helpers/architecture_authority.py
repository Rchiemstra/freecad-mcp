"""AST-backed inventory of temporary Python document-authority surfaces."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

_SYMBOL_PATTERNS = {
    "core_authority": re.compile(
        r".*(?:core_authority|authority_handoff|authority_rollback|"
        r"mutation_capability|sync_.*owner|set_.*owner|bump_takeover).*"
    ),
    "locked_error_handoff_rotation": re.compile(r".*claim_locked_error_handoff.*"),
    "lease_observers": re.compile(
        r"^(?:DocumentLeaseObserver|DocumentLockObserver|"
        r"(?:un)?register_(?:document_lease_observer|live_document_recovery))$"
    ),
    "heartbeats": re.compile(r".*heartbeat.*", re.I),
    "sidecar_correctness": re.compile(r".*(?:sidecar|FileBaseline|effective_record).*", re.I),
    "mcp_save_recovery_authority": re.compile(
        r".*(?:begin_save|commit_save_as|complete_local_save_and_clear|local_save|"
        r"local_restore|local_recovery|mark_save_verified|recover_orphaned|"
        r"recovery_authority|release_clean|run_legacy_save|run_typed_save).*"
    ),
}
_IMPLICIT_PATH_PATTERNS = {
    "core_authority": re.compile(r"/document_lease/core_authority(?:\.py|_ops/)"),
    "locked_error_handoff_rotation": re.compile(r"locked_error_handoff|handoff_continuation"),
    "lease_observers": re.compile(
        r"/document_lease/observer(?:\.py|_ops/)|document_lock_observer\.py|"
        r"document_lock_ops/registration\.py"
    ),
    "heartbeats": re.compile(r"heartbeat|stale_lease_recovery|server_ops/lifespan\.py"),
    "sidecar_correctness": re.compile(
        r"/document_lease/sidecar|document_lock_ops/(?:sidecar_io|mutation_check|registry_)|"
        r"document_lease/service_ops/(?:effective_records|foreign_|acquisition)|"
        r"rpc_helpers_ops/document_identity\.py|dispatch_core_unenforced\.py|"
        r"lock_indicator_ops/(?:active_leases|lease_|local_)|snapshot_service|save_service"
    ),
    "mcp_save_recovery_authority": re.compile(
        r"lease_methods_ops/(?:save_|release|reconcile|handoff)|"
        r"document_lease/service_ops/(?:recover_|recovery_|save_|release_clean)|"
        r"lock_indicator_ops/local_|rpc_server/lease_runtime|server_lifecycle|"
        r"freecad_client_ops/|stale_recovery|tools_lease_"
    ),
}


def _symbol_nodes(tree: ast.AST) -> list[tuple[ast.AST, str, str]]:
    symbols: list[tuple[ast.AST, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append((node, node.name, type(node).__name__))
        elif isinstance(node, ast.Name):
            symbols.append((node, node.id, "Name"))
        elif isinstance(node, ast.Attribute):
            symbols.append((node, node.attr, "Attribute"))
        elif isinstance(node, ast.alias):
            symbols.append((node, node.asname or node.name, "ImportAlias"))
    return symbols


def _is_git_sidecar(symbol: str) -> bool:
    compact = re.sub(r"[^a-z]", "", symbol.lower())
    return "gitsidecar" in compact


def authority_symbol_census(
    *, root: Path, production_files: list[Path]
) -> dict[str, list[dict[str, Any]]]:
    census: dict[str, list[dict[str, Any]]] = {}
    for authority_id, symbol_pattern in _SYMBOL_PATTERNS.items():
        records: list[dict[str, Any]] = []
        path_pattern = _IMPLICIT_PATH_PATTERNS[authority_id]
        for path in production_files:
            relative = path.relative_to(root).as_posix()
            # Phase 3 vendors one byte-identical protocol implementation into both
            # processes. Count the add-on copy once; byte equality independently
            # prevents the client vendor from hiding a divergent authority symbol.
            if relative.startswith("src/freecad_mcp/_shared/protocol/"):
                continue
            if authority_id == "sidecar_correctness" and path.name == "git_sidecar.py":
                continue
            if path_pattern.search(relative):
                records.append(
                    {"path": relative, "line": 0, "column": 0, "symbol": "<module>"}
                )
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node, symbol, kind in _symbol_nodes(tree):
                if not symbol_pattern.fullmatch(symbol):
                    continue
                if authority_id == "core_authority" and "windows_owner" in symbol:
                    continue
                if authority_id == "sidecar_correctness" and _is_git_sidecar(symbol):
                    continue
                records.append(
                    {
                        "path": relative,
                        "line": getattr(node, "lineno", 0),
                        "column": getattr(node, "col_offset", 0),
                        "symbol": symbol,
                        "kind": kind,
                    }
                )
        census[authority_id] = sorted(
            records,
            key=lambda item: (
                item["path"], item["line"], item["column"], item["symbol"]
            ),
        )
    return census
