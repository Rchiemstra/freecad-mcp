"""AST-backed inventory of temporary Python document-authority surfaces."""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path
from typing import Any


def _module_names(root: Path, path: Path) -> tuple[str, ...]:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    if parts[:2] == ["addon", "FreeCADMCP"]:
        canonical = ".".join(parts)
        return canonical, canonical.removeprefix("addon.")
    if parts[:2] == ["src", "freecad_mcp"]:
        return (".".join(parts[1:]),)
    return ()


def reachable_python_modules(
    *, root: Path, production_files: list[Path], entrypoints: tuple[str, ...]
) -> set[str]:
    """Return the static local-import closure from the live composition roots."""

    module_paths: dict[str, Path] = {}
    path_modules: dict[Path, str] = {}
    for path in production_files:
        names = _module_names(root, path)
        if not names:
            continue
        path_modules[path] = names[0]
        for name in names:
            module_paths[name] = path

    reachable: set[str] = set()
    pending = list(entrypoints)
    while pending:
        requested = pending.pop()
        path = module_paths.get(requested)
        if path is None:
            continue
        module = path_modules[path]
        if module in reachable:
            continue
        reachable.add(module)
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        class RuntimeImportVisitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.nodes: list[ast.Import | ast.ImportFrom] = []

            def visit_If(self, node: ast.If) -> None:
                type_only = (
                    isinstance(node.test, ast.Name)
                    and node.test.id == "TYPE_CHECKING"
                ) or (
                    isinstance(node.test, ast.Attribute)
                    and node.test.attr == "TYPE_CHECKING"
                )
                if type_only:
                    for statement in node.orelse:
                        self.visit(statement)
                    return
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                self.nodes.append(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                self.nodes.append(node)

        visitor = RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.nodes:
            candidates: list[str] = []
            if isinstance(node, ast.Import):
                candidates.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    relative_name = "." * node.level + (node.module or "")
                    try:
                        base = importlib.util.resolve_name(relative_name, package)
                    except (ImportError, ValueError):
                        continue
                else:
                    base = node.module or ""
                if base:
                    candidates.append(base)
                candidates.extend(
                    f"{base}.{alias.name}" if base else alias.name
                    for alias in node.names
                    if alias.name != "*"
                )
            for candidate in candidates:
                if candidate in module_paths:
                    pending.append(candidate)
                addon_candidate = f"addon.{candidate}"
                if addon_candidate in module_paths:
                    pending.append(addon_candidate)
    return reachable

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
    "heartbeats": re.compile(r".*heartbeat.*", re.IGNORECASE),
    "sidecar_correctness": re.compile(
        r".*(?:sidecar|FileBaseline|effective_record).*", re.IGNORECASE
    ),
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
    "heartbeats": re.compile(r"heartbeat|stale_lease_recovery"),
    "sidecar_correctness": re.compile(
        r"/document_lease/sidecar|document_lock_ops/(?:sidecar_io|mutation_check|registry_)|"
        r"document_lease/service_ops/(?:effective_records|foreign_|acquisition)|"
        r"rpc_helpers_ops/document_identity\.py|dispatch_core_unenforced\.py|"
        r"lock_indicator_ops/(?:active_leases|lease_|local_)|"
        r"snapshot_service_ops/(?:baseline_snapshot|recovery_paths|sidecar_permissions)|"
        r"save_service"
    ),
    "mcp_save_recovery_authority": re.compile(
        r"lease_methods_ops/(?:save_|release|reconcile|handoff)|"
        r"document_lease/service_ops/(?:recover_|recovery_|save_|release_clean)|"
        r"lock_indicator_ops/local_|rpc_server/lease_runtime|stale_recovery"
    ),
}
_HISTORIC_DECODER_SCOPES = {
    "addon/FreeCADMCP/document_lease/model.py": frozenset(
        {
            "HistoricLeaseRecord",
            "_freeze_historic_value",
            "_historic_hash",
            "_redact_historic_public_value",
            "_thaw_historic_value",
            "_validated_historic_payload",
            "decode_historic_lease_record",
        }
    ),
    "addon/FreeCADMCP/document_lease/historic_sidecar.py": frozenset(
        {
            "_decode_validated_historic_record",
            "_load_historic_json",
            "decode_historic_sidecar_bytes",
        }
    ),
}
_HISTORIC_DECODER_SIDECAR_SYMBOLS = {
    "addon/FreeCADMCP/document_lease/model.py": frozenset(
        {
            "SidecarMalformedError",
            "to_sidecar_dict",
            "validate_sidecar_payload",
        }
    ),
    "addon/FreeCADMCP/document_lease/historic_sidecar.py": frozenset(
        {
            "MAX_SIDECAR_BYTES",
            "SidecarMalformedError",
            "SidecarTooLargeError",
            "decode_historic_sidecar_bytes",
            "validate_sidecar_payload",
        }
    ),
}
_HISTORIC_DECODER_REEXPORTS = {
    "addon/FreeCADMCP/document_lease/sidecar.py": frozenset(
        {"decode_historic_sidecar_bytes"}
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


def _historic_decoder_nodes(tree: ast.Module, relative: str) -> set[ast.AST]:
    """Return nodes in the explicitly non-authoritative Phase 7 decoder seam."""

    scopes = _HISTORIC_DECODER_SCOPES.get(relative, frozenset())
    return {
        node
        for statement in tree.body
        if isinstance(statement, (ast.ClassDef, ast.FunctionDef))
        and statement.name in scopes
        for node in ast.walk(statement)
    }


def _skip_authority_path(authority_id: str, relative: str, path: Path) -> bool:
    if relative.startswith("src/freecad_mcp/_shared/protocol/"):
        return True
    if "/generated/capabilities/" in relative:
        return True
    return authority_id == "sidecar_correctness" and path.name == "git_sidecar.py"


def _skip_authority_symbol(
    authority_id: str,
    relative: str,
    symbol: str,
    node: ast.AST,
    historic_decoder_nodes: set[ast.AST],
) -> bool:
    if authority_id == "core_authority" and "windows_owner" in symbol:
        return True
    if authority_id != "sidecar_correctness":
        return False
    if _is_git_sidecar(symbol):
        return True
    if isinstance(node, ast.alias):
        return symbol in _HISTORIC_DECODER_REEXPORTS.get(
            relative, frozenset()
        ) or symbol in _HISTORIC_DECODER_SIDECAR_SYMBOLS.get(
            relative, frozenset()
        )
    return node in historic_decoder_nodes and symbol in (
        _HISTORIC_DECODER_SIDECAR_SYMBOLS.get(relative, frozenset())
    )


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
            if _skip_authority_path(authority_id, relative, path):
                continue
            pure_client_transport = (
                authority_id == "mcp_save_recovery_authority"
                and relative
                == "src/freecad_mcp/freecad_client_ops/json_rpc_http_transport.py"
            )
            if path_pattern.search(relative) and not pure_client_transport:
                records.append(
                    {"path": relative, "line": 0, "column": 0, "symbol": "<module>"}
                )
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            historic_decoder_nodes = _historic_decoder_nodes(tree, relative)
            for node, symbol, kind in _symbol_nodes(tree):
                if not symbol_pattern.fullmatch(symbol):
                    continue
                if _skip_authority_symbol(
                    authority_id,
                    relative,
                    symbol,
                    node,
                    historic_decoder_nodes,
                ):
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
