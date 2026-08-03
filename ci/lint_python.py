#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff>=0.9"]
# ///
"""Run Ruff and the FreeCAD MCP architectural boundary policy.

The policy deliberately measures ownership and dependency shape, not module size:

* ARCH101: one capability subject per implementation module;
* ARCH102: transport -> dispatch -> capabilities, never upward or into runtime;
* ARCH103: no application runtime module locator;
* ARCH104: no internal import through a package barrel;
* ARCH105: compatibility shims are declarative and side-effect free;
* ARCH106: explicit package public surfaces stay within their budget; and
* ARCH107: giant facades and mixed-responsibility grab bags are rejected.

Legacy findings are allowed only by exact records in
``ci/architecture_policy_allowances.json``. Ruff C901 remains the function-level
complexity rule.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tokenize
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

LINE_LENGTH = 100
TARGET_VERSION = "py311"
PUBLIC_SYMBOL_BUDGET = 16
RUFF_RULES = ("E", "F", "I", "UP", "B", "SIM", "C901", "RUF")
ALLOWANCE_FILE = Path("ci/architecture_policy_allowances.json")
POLICY_CODES = frozenset(f"ARCH10{number}" for number in range(1, 8))
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "architecture_policy_fixtures",
        "build",
        "dist",
        "generated",
        "node_modules",
        "site-packages",
        "third_party",
        "vendor",
        "venv",
    }
)
LAYER_ORDER = {"transport": 0, "dispatch": 1, "capabilities": 2}
RUNTIME_LOCATOR_MODULES = frozenset(
    {
        "core_authority",
        "document_lease",
        "document_lock",
        "rpc_server",
        "server",
    }
)
STDLIB_MODULES = frozenset(sys.stdlib_module_names)
SHIM_MARKERS = (
    "compatibility shim",
    "compatibility spelling",
    "deprecated import",
    "historic import",
    "import-only",
    "legacy import path",
    "shim-shaped",
)
CAPABILITY_TERMS: Mapping[str, frozenset[str]] = {
    "assembly": frozenset({"assembly", "joint"}),
    "diagnostics": frozenset({"diagnostic", "diagnostics", "health", "logging"}),
    "document": frozenset({"document", "recovery", "save"}),
    "drawing": frozenset({"drawing", "page"}),
    "execution": frozenset({"code", "command", "execute", "execution", "macro"}),
    "export": frozenset({"export", "importer", "serializer"}),
    "fem": frozenset({"fem", "material"}),
    "mesh": frozenset({"mesh", "topology"}),
    "object": frozenset({"object", "property"}),
    "path": frozenset({"path", "job"}),
    "render": frozenset({"render", "video"}),
    "sketch": frozenset({"sketch", "constraint", "geometry"}),
    "ui": frozenset({"dialog", "dock", "ui", "widget"}),
    "view": frozenset({"camera", "selection", "view"}),
    "worker": frozenset({"worker", "process"}),
}


@dataclass(frozen=True, order=True)
class Violation:
    path: str
    line: int
    column: int
    code: str
    message: str
    fingerprint: str


@dataclass(frozen=True)
class Allowance:
    code: str
    path: str
    line: int
    column: int
    fingerprint: str
    reason: str
    removal_phase: int


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    display: str
    source: str
    tree: ast.Module


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ruff plus the FreeCAD MCP architectural boundary policy."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to check; default is the current directory.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Relative path glob to exclude; may be repeated.",
    )
    parser.add_argument("--fix", action="store_true", help="Apply safe Ruff fixes.")
    parser.add_argument(
        "--architecture-only",
        action="store_true",
        help="Skip Ruff and run only the architectural boundary policy.",
    )
    return parser.parse_args(argv)


def display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def is_excluded(path: Path, root: Path, patterns: Sequence[str]) -> bool:
    relative = display_path(path, root)
    try:
        parts = path.resolve().relative_to(root).parts
    except ValueError:
        parts = path.parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    return any(Path(relative).match(pattern) for pattern in patterns)


def discover_files(
    requested: Sequence[str], root: Path, patterns: Sequence[str]
) -> list[Path]:
    found: set[Path] = set()
    for raw in requested:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if not candidate.exists():
            print(f"lint: path does not exist: {candidate}", file=sys.stderr)
            continue
        paths = [candidate] if candidate.is_file() else candidate.rglob("*.py")
        for path in paths:
            if path.is_file() and path.suffix == ".py":
                resolved = path.resolve()
                if not is_excluded(resolved, root, patterns):
                    found.add(resolved)
    return sorted(found, key=lambda path: display_path(path, root))


def read_source(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def _fingerprint(
    code: str, path: str, line: int, column: int, identity: str
) -> str:
    value = f"{code}|{path}|{line}|{column}|{identity}".encode()
    return hashlib.sha256(value).hexdigest()[:20]


def _violation(
    parsed: ParsedFile,
    node: ast.AST,
    code: str,
    message: str,
    identity: str,
) -> Violation:
    line = int(getattr(node, "lineno", 1))
    column = int(getattr(node, "col_offset", 0)) + 1
    return Violation(
        parsed.display,
        line,
        column,
        code,
        message,
        _fingerprint(code, parsed.display, line, column, identity),
    )


def _parse_files(files: Sequence[Path], root: Path) -> tuple[list[ParsedFile], list[Violation]]:
    parsed_files: list[ParsedFile] = []
    failures: list[Violation] = []
    for path in files:
        display = display_path(path, root)
        try:
            source = read_source(path)
        except (OSError, SyntaxError, UnicodeError) as exc:
            failures.append(
                Violation(
                    display,
                    1,
                    1,
                    "ARCH000",
                    f"cannot read source: {exc}",
                    _fingerprint("ARCH000", display, 1, 1, type(exc).__name__),
                )
            )
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            line = int(exc.lineno or 1)
            column = int(exc.offset or 1)
            failures.append(
                Violation(
                    display,
                    line,
                    column,
                    "ARCH000",
                    f"cannot parse source: {exc.msg}",
                    _fingerprint("ARCH000", display, line, column, exc.msg),
                )
            )
            continue
        parsed_files.append(ParsedFile(path, display, source, tree))
    return parsed_files, failures


def _import_targets(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    prefix = "." * node.level + (node.module or "")
    return [prefix]


def _module_package_parts(parsed: ParsedFile) -> list[str]:
    parts = list(Path(parsed.display).parts[:-1])
    if parts[:2] == ["addon", "FreeCADMCP"]:
        return parts
    if parts[:2] == ["src", "freecad_mcp"]:
        return ["freecad_mcp", *parts[2:]]
    anchors = {*LAYER_ORDER, "runtime"}
    for index, part in enumerate(parts):
        if part in anchors:
            return parts[index:]
    return parts


def _resolved_import_targets(
    parsed: ParsedFile, node: ast.Import | ast.ImportFrom
) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level:
        package = _module_package_parts(parsed)
        retained = max(0, len(package) - (node.level - 1))
        base_parts = [*package[:retained], *(node.module or "").split(".")]
        base_parts = [part for part in base_parts if part]
        base = ".".join(base_parts)
    else:
        base = node.module or ""
    targets = [base] if base else []
    targets.extend(".".join(part for part in (base, alias.name) if part) for alias in node.names)
    return list(dict.fromkeys(targets))


def _local_import_targets(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Match the frozen Phase 1 local-singleton-import census exactly."""

    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    prefix = "." * node.level + (node.module or "")
    separator = "" if not prefix or prefix.endswith(".") else "."
    return [f"{prefix}{separator}{alias.name}" for alias in node.names]


def _component_after(parts: Sequence[str], component: str) -> str | None:
    try:
        index = parts.index(component)
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None


def _file_layer(parsed: ParsedFile) -> str | None:
    parts = tuple(part for part in parsed.display.replace("\\", "/").split("/") if part)
    if "FreeCADMCP" in parts:
        index = parts.index("FreeCADMCP") + 1
        return parts[index] if index < len(parts) and parts[index] in LAYER_ORDER else None
    return parts[0] if parts and parts[0] in LAYER_ORDER else None


def _module_layer(module: str) -> str | None:
    parts = module.lstrip(".").split(".")
    if parts[:2] == ["addon", "FreeCADMCP"]:
        parts = parts[2:]
    elif parts and parts[0] in {"FreeCADMCP", "freecad_mcp"}:
        parts = parts[1:]
    return parts[0] if parts and parts[0] in LAYER_ORDER else None


def _is_addon_runtime_module(module: str) -> bool:
    parts = module.lstrip(".").split(".")
    if parts[:2] == ["addon", "FreeCADMCP"]:
        parts = parts[2:]
    elif parts and parts[0] in {"FreeCADMCP", "freecad_mcp"}:
        parts = parts[1:]
    return parts == ["runtime"]


def _is_permitted_gateway_import(module: str) -> bool:
    parts = module.lstrip(".").split(".")
    if not parts or parts[0] in STDLIB_MODULES:
        return True
    if parts[:2] == ["addon", "FreeCADMCP"] or parts[0] in {
        "FreeCADMCP",
        "freecad_mcp",
    }:
        return True
    return parts[0] in {*LAYER_ORDER, "_shared", "runtime"}


def _check_layer_direction(parsed: ParsedFile) -> list[Violation]:
    current = _file_layer(parsed)
    if current is None:
        return []
    findings: list[Violation] = []
    bindings = _import_bindings(parsed.tree)
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.Call):
            findings.extend(_dynamic_layer_findings(parsed, current, node, bindings))
        elif isinstance(node, ast.Import | ast.ImportFrom):
            findings.extend(_static_layer_findings(parsed, current, node))
    return findings


def _dynamic_layer_findings(
    parsed: ParsedFile,
    current: str,
    node: ast.Call,
    bindings: Mapping[str, str],
) -> list[Violation]:
    dynamic_import = _dynamic_import_call(node, bindings)
    if dynamic_import is None:
        return []
    function_name, literal_target, target_text = dynamic_import
    findings = (
        _dynamic_direction_findings(
            parsed, current, node, function_name, literal_target
        )
        if literal_target is not None
        else []
    )
    if current in {"transport", "dispatch"} and (
        literal_target is None or not _is_permitted_gateway_import(literal_target)
    ):
        findings.append(
            _violation(
                parsed,
                node,
                "ARCH102",
                f"{current} layer may not dynamically import non-stdlib "
                f"runtime {target_text} via {function_name}",
                f"dynamic:{current}:{function_name}:{target_text}",
            )
        )
    return findings


def _dynamic_direction_findings(
    parsed: ParsedFile,
    current: str,
    node: ast.Call,
    function_name: str,
    target: str,
) -> list[Violation]:
    if _is_addon_runtime_module(target):
        return [
            _violation(
                parsed,
                node,
                "ARCH102",
                f"{current} layer may not dynamically import runtime via {target}",
                f"dynamic-runtime:{current}:{function_name}:{target}",
            )
        ]
    target_layer = _module_layer(target)
    if target_layer is None or LAYER_ORDER[target_layer] >= LAYER_ORDER[current]:
        return []
    return [
        _violation(
            parsed,
            node,
            "ARCH102",
            f"{current} may not dynamically import {target_layer} via {target}; "
            "dependencies point transport -> dispatch -> capabilities",
            f"dynamic-upward:{current}:{target_layer}:{function_name}:{target}",
        )
    ]


def _static_layer_findings(
    parsed: ParsedFile,
    current: str,
    node: ast.Import | ast.ImportFrom,
) -> list[Violation]:
    findings: list[Violation] = []
    reported: set[tuple[str, str]] = set()
    for target in _resolved_import_targets(parsed, node):
        target_parts = target.lstrip(".").split(".")
        target_layer = _module_layer(target)
        if _is_addon_runtime_module(target) and ("runtime", "runtime") not in reported:
            reported.add(("runtime", "runtime"))
            findings.append(
                _violation(
                    parsed,
                    node,
                    "ARCH102",
                    f"{current} layer may not import runtime via {target}",
                    f"runtime:{current}:{target}",
                )
            )
        elif (
            target_layer is not None
            and LAYER_ORDER[target_layer] < LAYER_ORDER[current]
            and ("layer", target_layer) not in reported
        ):
            reported.add(("layer", target_layer))
            findings.append(
                _violation(
                    parsed,
                    node,
                    "ARCH102",
                    f"{current} may not import {target_layer} via {target}; dependencies "
                    "point transport -> dispatch -> capabilities",
                    f"upward:{current}:{target_layer}:{target}",
                )
            )
        if (
            current in {"transport", "dispatch"}
            and not _is_permitted_gateway_import(target)
            and ("freecad", target_parts[0]) not in reported
        ):
            reported.add(("freecad", target_parts[0]))
            findings.append(
                _violation(
                    parsed,
                    node,
                    "ARCH102",
                    f"{current} layer may not import non-stdlib runtime "
                    f"{target_parts[0]} directly",
                    f"freecad:{current}:{target}",
                )
            )
    return findings


def _dynamic_import_call(
    node: ast.Call, bindings: Mapping[str, str]
) -> tuple[str, str | None, str] | None:
    function_name = _qualified_name(node.func, bindings)
    if function_name not in {
        "__import__",
        "builtins.__import__",
        "importlib.import_module",
    }:
        return None
    argument = node.args[0] if node.args else None
    literal_target = _string_constant(argument)
    return function_name, literal_target, _expression_text(argument)


def _words(value: str) -> set[str]:
    result: set[str] = set()
    current: list[str] = []
    for character in value:
        if character.isalnum():
            if character.isupper() and current:
                result.add("".join(current).lower())
                current = [character]
            else:
                current.append(character)
        elif current:
            result.add("".join(current).lower())
            current = []
    if current:
        result.add("".join(current).lower())
    return result


def _module_executed_nodes(tree: ast.Module) -> Iterator[ast.AST]:
    stack: list[ast.AST] = list(reversed(tree.body))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _import_bound_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.asname or alias.name.split(".", maxsplit=1)[0] for alias in node.names]
    return [alias.asname or alias.name for alias in node.names if alias.name != "*"]


def _module_binding_names(tree: ast.Module, *, include_imports: bool) -> set[str]:
    comprehension_target_ids = {
        id(target)
        for node in _module_executed_nodes(tree)
        if isinstance(node, ast.comprehension)
        for target in ast.walk(node.target)
        if isinstance(target, ast.Name)
    }
    names = {
        node.id
        for node in _module_executed_nodes(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del)
        and id(node) not in comprehension_target_ids
    }
    for node in _module_executed_nodes(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif include_imports and isinstance(node, ast.Import | ast.ImportFrom):
            names.update(_import_bound_names(node))
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            names.add(node.name)
    return names


def _declared_words(tree: ast.Module) -> set[str]:
    words = {
        word
        for name in _module_binding_names(tree, include_imports=False)
        for word in _words(name)
    }
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            for member in node.body:
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                    words.update(_words(member.name))
    return words


def _internal_capability_subject(module: str) -> str | None:
    parts = module.lstrip(".").split(".")
    prefixes = (
        ["addon", "FreeCADMCP", "capabilities"],
        ["FreeCADMCP", "capabilities"],
        ["freecad_mcp", "capabilities"],
        ["capabilities"],
    )
    for prefix in prefixes:
        if parts[: len(prefix)] == prefix and len(parts) > len(prefix):
            return parts[len(prefix)]
    return None


def _capability_subjects(parsed: ParsedFile) -> set[str]:
    words = _words(parsed.path.stem) | _declared_words(parsed.tree)
    imported_subjects: set[str] = set()
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            targets = _resolved_import_targets(parsed, node)
            subjects = {
                subject
                for target in targets
                if (subject := _internal_capability_subject(target))
            }
            imported_subjects.update(subjects)
    vocabulary_subjects = {
        subject
        for subject, terms in CAPABILITY_TERMS.items()
        if words.intersection(terms)
    }
    return imported_subjects | vocabulary_subjects


def _static_string_list(
    node: ast.AST, values: Mapping[str, list[str]]
) -> list[str] | None:
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        result: list[str] = []
        for element in node.elts:
            if isinstance(element, ast.Starred):
                nested = _static_string_list(element.value, values)
                if nested is None:
                    return None
                result.extend(nested)
            elif isinstance(element, ast.Constant) and isinstance(element.value, str):
                result.append(element.value)
            else:
                return None
        return result
    if isinstance(node, ast.Name):
        return values.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string_list(node.left, values)
        right = _static_string_list(node.right, values)
        return None if left is None or right is None else [*left, *right]
    return None


def _binding_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Starred):
        return _binding_names(node.value)
    if isinstance(node, ast.List | ast.Tuple):
        return [name for element in node.elts for name in _binding_names(element)]
    return []


def _assigned_names_and_value(node: ast.stmt) -> tuple[list[str], ast.AST | None]:
    if isinstance(node, ast.Assign):
        names = [name for target in node.targets for name in _binding_names(target)]
        return names, node.value
    if isinstance(node, ast.AnnAssign):
        return _binding_names(node.target), node.value
    return [], None


def _all_mutation(
    node: ast.stmt, values: Mapping[str, list[str]]
) -> tuple[bool, list[str] | None]:
    if (
        isinstance(node, ast.AugAssign)
        and _targets_all(node.target)
    ):
        if not isinstance(node.target, ast.Name):
            return True, None
        extension = _static_string_list(node.value, values)
        current = values.get("__all__")
        if isinstance(node.op, ast.Add) and current is not None and extension is not None:
            return True, [*current, *extension]
        return True, None
    is_call = (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "__all__"
    )
    is_destructive_assignment = (
        isinstance(node, ast.Assign)
        and any(
            _targets_all(target) and not isinstance(target, ast.Name)
            for target in node.targets
        )
    ) or (
        isinstance(node, ast.AnnAssign)
        and _targets_all(node.target)
        and not isinstance(node.target, ast.Name)
    ) or (
        isinstance(node, ast.Delete)
        and any(_targets_all(target) for target in node.targets)
    )
    is_root_rebinding = (
        isinstance(
            node,
            ast.FunctionDef
            | ast.AsyncFunctionDef
            | ast.ClassDef
            | ast.Import
            | ast.ImportFrom,
        )
        and _mutates_all(node)
    )
    is_nested = _nested_all_mutation(node) is not None
    return (
        (True, None)
        if is_call or is_destructive_assignment or is_root_rebinding or is_nested
        else (False, None)
    )


def _module_executed_descendants(node: ast.AST) -> Iterator[ast.AST]:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
        return
    stack = list(ast.iter_child_nodes(node))
    while stack:
        nested = stack.pop()
        yield nested
        if isinstance(nested, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(nested))


def _targets_all(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "__all__"
    if isinstance(node, ast.Attribute | ast.Subscript | ast.Starred):
        return _targets_all(node.value)
    if isinstance(node, ast.List | ast.Tuple):
        return any(_targets_all(element) for element in node.elts)
    return False


def _mutates_all(node: ast.AST) -> bool:
    assigned = (
        list(node.targets)
        if isinstance(node, ast.Assign)
        else [node.target]
        if isinstance(node, ast.AnnAssign | ast.AugAssign)
        else [node.target]
        if isinstance(node, ast.NamedExpr)
        else list(node.targets)
        if isinstance(node, ast.Delete)
        else []
    )
    is_assignment = any(_targets_all(target) for target in assigned)
    is_call = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "__all__"
    )
    is_name_store = (
        isinstance(node, ast.Name)
        and node.id == "__all__"
        and isinstance(node.ctx, ast.Store | ast.Del)
    )
    is_named_definition = (
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.name == "__all__"
    )
    is_import = isinstance(node, ast.Import | ast.ImportFrom) and "__all__" in (
        _import_bound_names(node)
    )
    is_named_handler = (
        isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar)
        and node.name == "__all__"
    )
    return (
        is_assignment
        or is_call
        or is_name_store
        or is_named_definition
        or is_import
        or is_named_handler
    )


def _nested_all_mutation(node: ast.AST) -> ast.AST | None:
    ignored: set[int] = set()
    if isinstance(node, ast.Assign):
        ignored.update(
            id(target)
            for target in node.targets
            if isinstance(target, ast.Name) and target.id == "__all__"
        )
    elif (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__all__"
    ):
        ignored.add(id(node.target))
    for nested in _module_executed_descendants(node):
        if id(nested) not in ignored and _mutates_all(nested):
            return nested
    return None


def _explicit_all(tree: ast.Module) -> tuple[list[str] | None, ast.AST | None]:
    values: dict[str, list[str]] = {}

    explicit: list[str] | None = None
    owner: ast.AST | None = None
    for node in tree.body:
        is_mutation, mutated = _all_mutation(node, values)
        if is_mutation:
            owner = node
            explicit = mutated
            if mutated is not None:
                values["__all__"] = explicit
            else:
                values.pop("__all__", None)
            continue
        names, value_node = _assigned_names_and_value(node)
        if value_node is None:
            continue
        if "__all__" in names:
            owner = node
        value = _static_string_list(value_node, values)
        if value is None:
            if "__all__" in names:
                explicit = None
                values.pop("__all__", None)
            continue
        for name in names:
            values[name] = value
            if name == "__all__":
                explicit = value
                owner = node
    return explicit, owner


def _public_names(parsed: ParsedFile) -> list[str]:
    explicit, _ = _explicit_all(parsed.tree)
    methods = [
        member.name
        for node in parsed.tree.body
        if isinstance(node, ast.ClassDef)
        and not node.name.startswith("_")
        for member in node.body
        if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
        and not member.name.startswith("_")
    ]
    public_bindings = sorted(
        name
        for name in _module_binding_names(parsed.tree, include_imports=True)
        if not name.startswith("_")
    )
    return list(
        dict.fromkeys([*(explicit or ()), *public_bindings, *methods])
    )


def _check_capability_ownership(parsed: ParsedFile) -> list[Violation]:
    subjects = _capability_subjects(parsed)
    path_parts = parsed.path.parts
    display_parts = tuple(
        part for part in parsed.display.replace("\\", "/").split("/") if part
    )
    declared_subject = _component_after(path_parts, "capabilities")
    findings: list[Violation] = []
    cross_subjects: set[str] = set()

    if declared_subject and declared_subject.endswith(".py"):
        declared_subject = None
    for node in ast.walk(parsed.tree):
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        reported_subjects: set[str] = set()
        for target in _resolved_import_targets(parsed, node):
            target_subject = _internal_capability_subject(target)
            if (
                declared_subject
                and target_subject
                and target_subject != declared_subject
                and target_subject not in reported_subjects
            ):
                reported_subjects.add(target_subject)
                cross_subjects.add(target_subject)
                findings.append(
                    _violation(
                        parsed,
                        node,
                        "ARCH101",
                        f"{declared_subject} imports capability subject {target_subject} "
                        f"via {target}",
                        f"cross-subject:{declared_subject}:{target_subject}:{target}",
                    )
                )

    mixed_root = len(subjects) >= 2
    layer = _file_layer(parsed)
    is_top_level_runtime = parsed.path.name == "runtime.py" and (
        len(display_parts) == 1 or display_parts[-2] == "FreeCADMCP"
    )
    is_composition = is_top_level_runtime or layer in {"transport", "dispatch"}
    unreported_foreign = (
        subjects
        - ({declared_subject} if declared_subject else set())
        - cross_subjects
    )
    owns_mixed_subjects = (
        (declared_subject is None and mixed_root)
        or (declared_subject is not None and bool(unreported_foreign))
    )
    if owns_mixed_subjects and not is_composition:
        owner: ast.AST = parsed.tree.body[0] if parsed.tree.body else parsed.tree
        findings.append(
            _violation(
                parsed,
                owner,
                "ARCH101",
                "module owns multiple capability subjects: " + ", ".join(sorted(subjects)),
                "subjects:" + ",".join(sorted(subjects)),
            )
        )
    return findings


def _string_constant(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _expression_text(node: ast.AST | None) -> str:
    if node is None:
        return "<missing>"
    constant = _string_constant(node)
    return repr(constant) if constant is not None else ast.dump(node, annotate_fields=False)


def _rpc_mod_node_finding(parsed: ParsedFile, node: ast.AST) -> Violation | None:
    message = "runtime locator _rpc_mod is forbidden; inject the collaborator"
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "_rpc_mod":
        return _violation(parsed, node, "ARCH103", message, "rpc-mod-definition")
    if (
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id == "_rpc_mod"
    ):
        return _violation(
            parsed, node, "ARCH103", message, f"rpc-mod-name:{type(node.ctx).__name__}"
        )
    if isinstance(node, ast.Attribute) and node.attr == "_rpc_mod":
        return _violation(parsed, node, "ARCH103", message, "rpc-mod-attribute")
    return None


def _import_locator_findings(
    parsed: ParsedFile, node: ast.Import | ast.ImportFrom
) -> list[Violation]:
    findings = [
        _violation(
            parsed,
            node,
            "ARCH103",
            "runtime locator _rpc_mod may not be imported",
            f"rpc-mod-import:{alias.name}:{alias.asname}",
        )
        for alias in node.names
        if alias.name == "_rpc_mod" or alias.name.endswith("._rpc_mod")
    ]
    paired_fallbacks = _paired_fallback_from_imports(parsed.tree)
    if isinstance(node, ast.ImportFrom):
        imported_runtime_names = {
            alias.name
            for alias in node.names
            if alias.name in RUNTIME_LOCATOR_MODULES
        }
        is_anchored_absolute = (node.module or "").startswith(
            ("addon.FreeCADMCP", "FreeCADMCP")
        )
        import_targets = (
            [
                target
                for target in _local_import_targets(node)
                if target.rsplit(".", maxsplit=1)[-1] in imported_runtime_names
            ]
            if node.level or is_anchored_absolute
            else []
        )
    else:
        import_targets = _local_import_targets(node)
    locator_targets = [
        target
        for target in import_targets
        if _is_application_runtime_module(target)
        and not (
            isinstance(node, ast.ImportFrom)
            and id(node) in paired_fallbacks
        )
    ]
    findings.extend(
        _violation(
            parsed,
            node,
            "ARCH103",
            f"local import is an application runtime module locator: {target}",
            f"local-import:{target}",
        )
        for target in locator_targets
    )
    return findings


def _paired_fallback_from_imports(tree: ast.Module) -> set[int]:
    paired: set[int] = set()
    for try_node in (node for node in ast.walk(tree) if isinstance(node, ast.Try)):
        for occurrences in _fallback_import_occurrences(try_node).values():
            paired.update(_paired_fallback_occurrences(occurrences))
    return paired


def _fallback_import_occurrences(
    try_node: ast.Try,
) -> dict[str, list[tuple[ast.Import | ast.ImportFrom, int]]]:
    occurrences: dict[str, list[tuple[ast.Import | ast.ImportFrom, int]]] = {}
    arms = [try_node.body, *(handler.body for handler in try_node.handlers)]
    for arm_index, statements in enumerate(arms):
        for node in _fallback_arm_imports(statements):
            for alias in node.names:
                if alias.name in RUNTIME_LOCATOR_MODULES:
                    occurrences.setdefault(alias.name, []).append((node, arm_index))
    return occurrences


def _paired_fallback_occurrences(
    occurrences: list[tuple[ast.Import | ast.ImportFrom, int]],
) -> set[int]:
    bare_nodes = {
        id(node): (node, arm)
        for node, arm in occurrences
        if isinstance(node, ast.Import)
    }
    from_nodes = {
        id(node): (node, arm)
        for node, arm in occurrences
        if isinstance(node, ast.ImportFrom)
    }
    if len(bare_nodes) == 1 and len(from_nodes) == 1:
        _, bare_arm = next(iter(bare_nodes.values()))
        from_node, from_arm = next(iter(from_nodes.values()))
        return {id(from_node)} if bare_arm != from_arm else set()
    if bare_nodes or len(from_nodes) != 2:
        return set()
    from_occurrences = list(from_nodes.values())
    if from_occurrences[0][1] == from_occurrences[1][1]:
        return set()
    return {id(node) for node, _ in from_occurrences}


def _fallback_arm_imports(
    statements: list[ast.stmt],
) -> list[ast.Import | ast.ImportFrom]:
    imports: list[ast.Import | ast.ImportFrom] = []
    stack: list[ast.AST] = list(reversed(statements))
    scope_nodes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Import | ast.ImportFrom):
            imports.append(node)
            continue
        if isinstance(node, scope_nodes):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(node))))
    return imports


def _is_application_runtime_module(module: str) -> bool:
    parts = module.lstrip(".").split(".")
    if len(parts) == 1:
        return parts[0] in RUNTIME_LOCATOR_MODULES
    is_project_module = (
        parts[:2] == ["addon", "FreeCADMCP"]
        or parts[0] == "FreeCADMCP"
    )
    return is_project_module and parts[-1] in RUNTIME_LOCATOR_MODULES


def _import_bindings(tree: ast.Module) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    _extend_assignment_bindings(tree, bindings)
    return bindings


def _extend_assignment_bindings(tree: ast.Module, bindings: dict[str, str]) -> None:
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign | ast.AnnAssign)
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            names, value = _assigned_names_and_value(node)
            qualified = _qualified_name(value, bindings) if value is not None else None
            if qualified is None:
                continue
            for name in names:
                if bindings.get(name) != qualified:
                    bindings[name] = qualified
                    changed = True
        if not changed:
            break


def _qualified_name(node: ast.AST, bindings: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value, bindings)
        return f"{owner}.{node.attr}" if owner else None
    return None


def _call_locator_findings(
    parsed: ParsedFile, node: ast.Call, bindings: Mapping[str, str]
) -> list[Violation]:
    function = node.func
    function_name = _qualified_name(function, bindings)
    argument = node.args[0] if node.args else None
    target = _expression_text(argument)
    findings: list[Violation] = []
    if function_name == "importlib.import_module":
        findings.append(
            _violation(
                parsed,
                node,
                "ARCH103",
                f"runtime module locator importlib.import_module({target}) is forbidden",
                f"importlib:{target}",
            )
        )
    if function_name == "sys.modules.get":
        findings.append(
            _violation(
                parsed,
                node,
                "ARCH103",
                f"runtime module locator sys.modules.get({target}) is forbidden",
                f"sys-modules-get:{target}",
            )
        )
    literal_target = (
        argument.value
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        else None
    )
    if (
        function_name in {"__import__", "builtins.__import__"}
        and literal_target is not None
        and _is_application_runtime_module(literal_target)
    ):
        findings.append(
            _violation(
                parsed,
                node,
                "ARCH103",
                f"runtime module locator __import__({target}) is forbidden",
                f"builtin-import:{target}",
            )
        )
    return findings


def _subscript_locator_finding(
    parsed: ParsedFile, node: ast.Subscript, bindings: Mapping[str, str]
) -> Violation | None:
    if (
        not isinstance(node.ctx, ast.Load)
        or _qualified_name(node.value, bindings) != "sys.modules"
    ):
        return None
    target = _expression_text(node.slice)
    return _violation(
        parsed,
        node,
        "ARCH103",
        f"runtime module locator sys.modules[{target}] is forbidden",
        f"sys-modules-subscript:{target}",
    )


def _compare_locator_finding(
    parsed: ParsedFile, node: ast.Compare, bindings: Mapping[str, str]
) -> Violation | None:
    is_membership = (
        len(node.ops) == 1
        and isinstance(node.ops[0], ast.In)
        and len(node.comparators) == 1
        and _qualified_name(node.comparators[0], bindings) == "sys.modules"
    )
    if not is_membership:
        return None
    return _violation(
        parsed,
        node,
        "ARCH103",
        "runtime module locator membership test against sys.modules is forbidden",
        f"sys-modules-contains:{ast.dump(node, annotate_fields=False)}",
    )


def _check_runtime_locators(parsed: ParsedFile) -> list[Violation]:
    findings: list[Violation] = []
    bindings = _import_bindings(parsed.tree)
    for node in ast.walk(parsed.tree):
        rpc_mod_finding = _rpc_mod_node_finding(parsed, node)
        if rpc_mod_finding is not None:
            findings.append(rpc_mod_finding)
        if isinstance(node, ast.Import | ast.ImportFrom):
            findings.extend(_import_locator_findings(parsed, node))
        elif isinstance(node, ast.Call):
            findings.extend(_call_locator_findings(parsed, node, bindings))
        elif isinstance(node, ast.Subscript):
            finding = _subscript_locator_finding(parsed, node, bindings)
            if finding is not None:
                findings.append(finding)
        elif isinstance(node, ast.Compare):
            finding = _compare_locator_finding(parsed, node, bindings)
            if finding is not None:
                findings.append(finding)

    explicit, owner = _explicit_all(parsed.tree)
    if explicit and "_rpc_mod" in explicit and owner is not None:
        findings.append(
            _violation(
                parsed,
                owner,
                "ARCH103",
                "runtime locator _rpc_mod may not be exported",
                "rpc-mod-export",
            )
        )
    return findings


def _relative_module_directory(parsed: ParsedFile, node: ast.ImportFrom) -> Path:
    directory = parsed.path.parent
    for _ in range(max(0, node.level - 1)):
        directory = directory.parent
    if node.module:
        directory = directory.joinpath(*node.module.split("."))
    return directory


@cache
def _absolute_module_directory(root: Path, module: str) -> Path | None:
    parts = module.split(".")
    candidates = [root.joinpath(*parts)]
    if parts[:2] == ["addon", "FreeCADMCP"]:
        candidates.append(root / "addon" / "FreeCADMCP" / Path(*parts[2:]))
        candidates.append(root.joinpath(*parts[2:]))
    if parts and parts[0] == "FreeCADMCP":
        candidates.append(root / "addon" / "FreeCADMCP" / Path(*parts[1:]))
        candidates.append(root.joinpath(*parts[1:]))
    if parts and parts[0] == "freecad_mcp":
        candidates.append(root / "src" / "freecad_mcp" / Path(*parts[1:]))
        candidates.append(root.joinpath(*parts[1:]))
    return next(
        (candidate for candidate in candidates if (candidate / "__init__.py").is_file()),
        None,
    )


def _check_barrel_imports(parsed: ParsedFile, root: Path) -> list[Violation]:
    findings: list[Violation] = []
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.ImportFrom):
            package = (
                _relative_module_directory(parsed, node)
                if node.level
                else _absolute_module_directory(root, node.module or "")
            )
            if package is None or not (package / "__init__.py").is_file():
                continue
            children = {child.name: child for child in package.iterdir()}
            for alias in node.names:
                module_child = children.get(f"{alias.name}.py")
                child_module = module_child is not None and module_child.is_file()
                if child_module:
                    continue
                target = "." * node.level + (node.module or "")
                findings.append(
                    _violation(
                        parsed,
                        node,
                        "ARCH104",
                        f"internal barrel import {target or '.'}::{alias.name}; "
                        f"resolved barrel {display_path(package / '__init__.py', root)}; "
                        "import the defining leaf module",
                        f"from-barrel:{display_path(package, root)}:{alias.name}",
                    )
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                package = _absolute_module_directory(root, alias.name)
                if package is not None:
                    findings.append(
                        _violation(
                            parsed,
                            node,
                            "ARCH104",
                            f"internal barrel import {alias.name}; import the defining leaf module",
                            f"import-barrel:{display_path(package, root)}",
                        )
                    )
    return findings


def _is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _immutable_metadata(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Tuple):
        return all(_immutable_metadata(element) for element in node.elts)
    if isinstance(node, ast.Name | ast.Attribute):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _immutable_metadata(node.left) and _immutable_metadata(node.right)
    return False


def _deprecation_metadata(node: ast.AST) -> bool:
    return isinstance(node, ast.Dict) and all(
        key is not None and _immutable_metadata(key) and _immutable_metadata(value)
        for key, value in zip(node.keys, node.values, strict=True)
    )


def _declarative_assignment(node: ast.Assign | ast.AnnAssign) -> bool:
    names, value = _assigned_names_and_value(node)
    if value is None or not names:
        return False
    if names == ["__all__"]:
        return _static_string_list(value, {}) is not None
    if names == ["DEPRECATION"]:
        return _deprecation_metadata(value)
    return _immutable_metadata(value)


def _declarative_shim_statement(
    node: ast.stmt, bindings: Mapping[str, str]
) -> bool:
    if _is_docstring(node) or isinstance(node, ast.Import | ast.ImportFrom | ast.Pass):
        return True
    if isinstance(node, ast.Assign | ast.AnnAssign):
        return _declarative_assignment(node)
    if isinstance(node, ast.If):
        is_type_checking = _qualified_name(node.test, bindings) == "typing.TYPE_CHECKING"
        return (
            is_type_checking
            and not node.orelse
            and all(_declarative_shim_statement(item, bindings) for item in node.body)
        )
    if isinstance(node, ast.Try):
        return (
            bool(node.handlers)
            and not node.orelse
            and not node.finalbody
            and all(
                _qualified_name(handler.type, bindings) == "ImportError"
                and handler.name is None
                and _import_only_fallback_arm(handler.body)
                for handler in node.handlers
            )
            and _import_only_fallback_arm(node.body)
        )
    return False


def _import_only_fallback_arm(statements: list[ast.stmt]) -> bool:
    return bool(statements) and all(
        isinstance(item, ast.Import | ast.ImportFrom | ast.Pass) for item in statements
    )


def _check_shim_purity(parsed: ParsedFile) -> list[Violation]:
    docstring = ast.get_docstring(parsed.tree, clean=False) or ""
    header = "\n".join(parsed.source.splitlines()[:40])
    shim_text = f"{docstring}\n{header}".lower()
    _, owner = _explicit_all(parsed.tree)
    has_import = any(
        isinstance(node, ast.Import | ast.ImportFrom) for node in parsed.tree.body
    )
    public_definitions = any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and not node.name.startswith("_")
        for node in parsed.tree.body
    )
    marker_declared = any(marker in shim_text for marker in SHIM_MARKERS)
    structural_candidate = owner is not None and has_import and not public_definitions
    if not marker_declared and not structural_candidate:
        return []
    bindings = _import_bindings(parsed.tree)
    impure = [
        node
        for node in parsed.tree.body
        if not _declarative_shim_statement(node, bindings)
    ]
    if not impure:
        return []
    first = impure[0]
    details = ", ".join(f"{type(node).__name__}@{getattr(node, 'lineno', 1)}" for node in impure)
    return [
        _violation(
            parsed,
            first,
            "ARCH105",
            f"compatibility shim is not declarative and side-effect free: {details}",
            f"impure-shim:{details}",
        )
    ]


def _check_public_surface(parsed: ParsedFile) -> list[Violation]:
    explicit, owner = _explicit_all(parsed.tree)
    if owner is None:
        return []
    if explicit is None:
        return [
            _violation(
                parsed,
                owner,
                "ARCH106",
                "explicit __all__ is not statically auditable",
                f"public-surface-unresolved:{ast.dump(owner, annotate_fields=False)}",
            )
        ]
    if len(explicit) <= PUBLIC_SYMBOL_BUDGET:
        return []
    return [
        _violation(
            parsed,
            owner,
            "ARCH106",
            f"package exports {len(explicit)} public symbols; budget is {PUBLIC_SYMBOL_BUDGET}",
            "public-surface:" + ",".join(explicit),
        )
    ]


def _is_immutable_constant_expression(node: ast.AST, known_names: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return node.id in known_names
    if isinstance(node, ast.Tuple):
        return all(_is_immutable_constant_expression(item, known_names) for item in node.elts)
    if isinstance(node, ast.UnaryOp):
        return isinstance(node.op, ast.UAdd | ast.USub | ast.Invert) and (
            _is_immutable_constant_expression(node.operand, known_names)
        )
    if isinstance(node, ast.BinOp):
        return not isinstance(node.op, ast.MatMult) and all(
            _is_immutable_constant_expression(item, known_names)
            for item in (node.left, node.right)
        )
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "frozenset"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Set | ast.Tuple)
    ):
        return all(
            _is_immutable_constant_expression(item, known_names)
            for item in node.args[0].elts
        )
    return False


def _is_cohesive_constants_module(parsed: ParsedFile, public_names: list[str]) -> bool:
    if parsed.path.stem != "constants" or not public_names:
        return False
    if not all(name.isupper() for name in public_names):
        return False

    local_constants: set[str] = set()
    for node in parsed.tree.body:
        name: str | None = None
        value: ast.AST | None = None
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value = node.value
        if name is None or name.startswith("_"):
            continue
        if not name.isupper() or value is None:
            return False
        if not _is_immutable_constant_expression(value, local_constants):
            return False
        local_constants.add(name)
    return set(public_names) == local_constants


def _check_mixed_responsibility(parsed: ParsedFile) -> list[Violation]:
    public_names = _public_names(parsed)
    subjects = _capability_subjects(parsed)
    constants_module = _is_cohesive_constants_module(parsed, public_names)
    giant = len(public_names) >= 24 or (
        len(public_names) >= 12 and len(subjects) >= 3
    )
    mixed = len(subjects) >= 3 and len(public_names) >= 7
    if constants_module and not mixed:
        return []
    if not giant and not mixed:
        return []
    owner: ast.AST = parsed.tree.body[0] if parsed.tree.body else parsed.tree
    if giant:
        message = f"giant public facade exposes {len(public_names)} symbols"
    else:
        message = (
            f"mixed-responsibility grab bag exposes {len(public_names)} symbols across "
            + ", ".join(sorted(subjects))
        )
    return [
        _violation(
            parsed,
            owner,
            "ARCH107",
            message,
            f"shape:{len(public_names)}:{','.join(sorted(subjects))}",
        )
    ]


def scan_architecture(files: Sequence[Path], root: Path) -> list[Violation]:
    """Return raw policy findings without applying legacy allowances."""

    parsed_files, failures = _parse_files(files, root)
    findings = list(failures)
    for parsed in parsed_files:
        findings.extend(_check_capability_ownership(parsed))
        findings.extend(_check_layer_direction(parsed))
        findings.extend(_check_runtime_locators(parsed))
        findings.extend(_check_barrel_imports(parsed, root))
        findings.extend(_check_shim_purity(parsed))
        findings.extend(_check_public_surface(parsed))
        findings.extend(_check_mixed_responsibility(parsed))
    return sorted(set(findings))


def scan_runtime_locators(files: Sequence[Path], root: Path) -> list[Violation]:
    """Return only raw ARCH103 findings, used to audit the frozen Phase 1 census."""

    parsed_files, failures = _parse_files(files, root)
    findings = list(failures)
    for parsed in parsed_files:
        findings.extend(_check_runtime_locators(parsed))
    return sorted(set(findings))


def load_allowances(path: Path) -> list[Allowance]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("allowances"), list):
        raise ValueError("allowance file must use schema_version 1 and an allowances list")
    allowances: list[Allowance] = []
    identities: set[tuple[str, str, int, int, str]] = set()
    for index, item in enumerate(payload["allowances"]):
        if not isinstance(item, dict):
            raise ValueError(f"allowance {index} is not an object")
        allowance = Allowance(
            code=str(item.get("code", "")),
            path=str(item.get("path", "")),
            line=int(item.get("line", 0)),
            column=int(item.get("column", 0)),
            fingerprint=str(item.get("fingerprint", "")),
            reason=str(item.get("reason", "")),
            removal_phase=int(item.get("removal_phase", 0)),
        )
        if allowance.code not in POLICY_CODES:
            raise ValueError(f"allowance {index} has unknown code {allowance.code!r}")
        if not allowance.path or any(character in allowance.path for character in "*?[]"):
            raise ValueError(f"allowance {index} path must be exact and contain no glob")
        if allowance.line < 1 or allowance.column < 1 or len(allowance.fingerprint) != 20:
            raise ValueError(f"allowance {index} has invalid position or fingerprint")
        if not allowance.reason or not 3 <= allowance.removal_phase <= 23:
            raise ValueError(f"allowance {index} needs a reason and removal phase 3..23")
        identity = (
            allowance.code,
            allowance.path,
            allowance.line,
            allowance.column,
            allowance.fingerprint,
        )
        if identity in identities:
            raise ValueError(f"allowance {index} duplicates {identity}")
        identities.add(identity)
        allowances.append(allowance)
    return allowances


def _scope_prefixes(requested: Sequence[str], root: Path) -> list[str]:
    prefixes: list[str] = []
    for raw in requested:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        prefixes.append(display_path(candidate, root).rstrip("/"))
    return prefixes


def _in_scope(path: str, prefixes: Sequence[str]) -> bool:
    return any(
        prefix in {"", "."} or path == prefix or path.startswith(prefix + "/")
        for prefix in prefixes
    )


def apply_allowances(
    findings: Sequence[Violation],
    allowances: Sequence[Allowance],
    scope_prefixes: Sequence[str] = (),
) -> list[Violation]:
    allowed = {
        (item.code, item.path, item.line, item.column, item.fingerprint): item
        for item in allowances
    }
    matched: set[tuple[str, str, int, int, str]] = set()
    remaining: list[Violation] = []
    for finding in findings:
        identity = (
            finding.code,
            finding.path,
            finding.line,
            finding.column,
            finding.fingerprint,
        )
        if identity in allowed:
            matched.add(identity)
        else:
            remaining.append(finding)
    if scope_prefixes:
        for identity, allowance in allowed.items():
            if identity in matched or not _in_scope(allowance.path, scope_prefixes):
                continue
            message = (
                f"stale architecture allowance for {allowance.code} must be removed or refreshed: "
                f"{allowance.reason}"
            )
            remaining.append(
                Violation(
                    allowance.path,
                    allowance.line,
                    allowance.column,
                    "ARCH099",
                    message,
                    _fingerprint(
                        "ARCH099",
                        allowance.path,
                        allowance.line,
                        allowance.column,
                        allowance.fingerprint,
                    ),
                )
            )
    return sorted(remaining)


def check_architecture(
    files: Sequence[Path],
    root: Path,
    *,
    allowance_path: Path | None = None,
    scope_prefixes: Sequence[str] = (),
) -> list[Violation]:
    path = allowance_path if allowance_path is not None else root / ALLOWANCE_FILE
    return apply_allowances(scan_architecture(files, root), load_allowances(path), scope_prefixes)


def ruff_command() -> list[str] | None:
    executable = shutil.which("ruff")
    if executable:
        return [executable]
    if importlib.util.find_spec("ruff") is not None:
        return [sys.executable, "-m", "ruff"]
    return None


def run_ruff(files: Sequence[Path], fix: bool) -> int:
    prefix = ruff_command()
    if prefix is None:
        print(
            "lint: Ruff is unavailable. Use 'uv run ci/lint_python.py' or "
            "install it with 'uv add --dev ruff'.",
            file=sys.stderr,
        )
        return 2

    exit_code = 0
    for start in range(0, len(files), 100):
        command = [
            *prefix,
            "check",
            "--isolated",
            "--select",
            ",".join(RUFF_RULES),
            "--line-length",
            str(LINE_LENGTH),
            "--target-version",
            TARGET_VERSION,
            "--output-format",
            "concise",
        ]
        if fix:
            command.append("--fix")
        command.extend(str(path) for path in files[start : start + 100])
        result = subprocess.run(command, check=False)
        if result.returncode:
            exit_code = result.returncode
    return exit_code


def run_ruff_source(path: Path, filename: str) -> subprocess.CompletedProcess[str]:
    """Run Ruff on a non-discoverable negative source fixture."""

    prefix = ruff_command()
    if prefix is None:
        raise RuntimeError("Ruff is unavailable")
    command = [
        *prefix,
        "check",
        "--isolated",
        "--select",
        ",".join(RUFF_RULES),
        "--line-length",
        str(LINE_LENGTH),
        "--target-version",
        TARGET_VERSION,
        "--output-format",
        "concise",
        "--stdin-filename",
        filename,
        "-",
    ]
    return subprocess.run(
        command,
        input=read_source(path),
        text=True,
        check=False,
        capture_output=True,
    )


def allowance_records(findings: Iterable[Violation]) -> list[dict[str, Any]]:
    """Serialize raw findings for an integrator-reviewed allowance manifest."""

    reasons = {
        "ARCH101": ("legacy mixed capability ownership", 22),
        "ARCH102": ("legacy layer-direction dependency", 17),
        "ARCH103": ("Phase 1 frozen runtime locator", 17),
        "ARCH104": ("legacy package-barrel import", 23),
        "ARCH105": ("legacy compatibility module with runtime behavior", 22),
        "ARCH106": ("legacy package public surface", 23),
        "ARCH107": ("legacy mixed-responsibility facade", 22),
    }
    records: list[dict[str, Any]] = []
    for finding in sorted(findings):
        if finding.code not in reasons:
            continue
        reason, removal_phase = reasons[finding.code]
        records.append(
            {
                "code": finding.code,
                "path": finding.path,
                "line": finding.line,
                "column": finding.column,
                "fingerprint": finding.fingerprint,
                "reason": f"{reason}: {finding.message}",
                "removal_phase": removal_phase,
            }
        )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path.cwd().resolve()
    files = discover_files(args.paths, root, args.exclude)
    if not files:
        print("lint: no Python files found", file=sys.stderr)
        return 2

    print(f"lint: checking {len(files)} Python files")
    try:
        violations = check_architecture(
            files,
            root,
            scope_prefixes=_scope_prefixes(args.paths, root),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"lint: invalid architecture allowance file: {exc}", file=sys.stderr)
        return 2
    for item in violations:
        print(f"{item.path}:{item.line}:{item.column}: {item.code} {item.message}")

    ruff_result = 0
    if not args.architecture_only:
        ruff_result = run_ruff(files, args.fix)
    if violations or ruff_result:
        return 1 if ruff_result in {0, 1} else ruff_result
    print("lint: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
