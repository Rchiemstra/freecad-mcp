"""Adversarial architecture contracts for the add-on transport layer."""

from __future__ import annotations

import ast
import importlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from ci import lint_python
from tests.helpers.architecture_authority import authority_symbol_census

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "addon" / "FreeCADMCP"
TRANSPORT_ROOT = ADDON_ROOT / "transport"
RPC_SERVER_PATH = ADDON_ROOT / "rpc_server" / "rpc_server.py"

pytestmark = pytest.mark.unit

_FORBIDDEN_RUNTIME_ROOTS = frozenset(
    {
        "Draft",
        "DraftVecUtils",
        "FreeCAD",
        "FreeCADGui",
        "Import",
        "Part",
        "Path",
        "PySide",
        "PySide2",
        "PySide6",
        "Qt",
        "Sketcher",
        "Spreadsheet",
        "WebGui",
        "pivy",
    }
)


def _transport_files() -> list[Path]:
    files = sorted(TRANSPORT_ROOT.rglob("*.py"))
    assert files, "Phase 9 must provide the canonical transport package"
    return files


def _module_name(path: Path) -> str:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        parts = path.with_suffix("").parts
        addon_index = max(
            index
            for index in range(len(parts) - 1)
            if parts[index : index + 2] == ("addon", "FreeCADMCP")
        )
        relative = Path(*parts[addon_index:])
    return ".".join(relative.with_suffix("").parts)


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        parts = path.parts
        addon_index = max(
            index
            for index in range(len(parts) - 1)
            if parts[index : index + 2] == ("addon", "FreeCADMCP")
        )
        return Path(*parts[addon_index:]).as_posix()


def _resolved_imports(path: Path, tree: ast.AST) -> list[tuple[ast.AST, str]]:
    current_package = _module_name(path).split(".")[:-1]
    imports: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node, alias.name) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            retained = max(0, len(current_package) - (node.level - 1))
            parts = [
                *current_package[:retained],
                *((node.module or "").split(".")),
            ]
            base = ".".join(part for part in parts if part)
        else:
            base = node.module or ""
        imports.append((node, base))
    return imports


def _permitted_import(target: str) -> bool:
    parts = target.lstrip(".").split(".")
    if not parts or not parts[0]:
        return False
    if parts[0] in sys.stdlib_module_names or parts[0] == "__future__":
        return True
    normalized = target.lstrip(".")
    return normalized in {
        "_shared.protocol",
        "addon.FreeCADMCP._shared.protocol",
        "addon.FreeCADMCP.transport",
    } or normalized.startswith(
        (
            "_shared.protocol.",
            "addon.FreeCADMCP._shared.protocol.",
            "addon.FreeCADMCP.transport.",
        )
    )


def _qualified_name(node: ast.AST, bindings: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value, bindings)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _assignment_pairs(
    target: ast.AST, value: ast.AST
) -> list[tuple[str, ast.AST]]:
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
    ):
        return [
            pair
            for target_item, value_item in zip(target.elts, value.elts, strict=True)
            for pair in _assignment_pairs(target_item, value_item)
        ]
    return []


def _import_bindings(tree: ast.AST) -> dict[str, str]:
    bindings: dict[str, str] = {
        "__import__": "builtins.__import__",
        "getattr": "builtins.getattr",
    }
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.partition(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                bindings[alias.asname or alias.name] = ".".join(
                    part for part in (module, alias.name) if part
                )
        elif isinstance(node, ast.Assign):
            assignments.extend(
                pair
                for target in node.targets
                for pair in _assignment_pairs(target, node.value)
            )
        elif isinstance(node, ast.AnnAssign):
            assignments.extend(_assignment_pairs(node.target, node.value))
    changed = True
    while changed:
        changed = False
        for target, expression in assignments:
            value = _qualified_name(expression, bindings)
            if value and bindings.get(target) != value:
                bindings[target] = value
                changed = True
    return bindings


def _static_string(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left, constants)
        right = _static_string(node.right, constants)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.FormattedValue):
        return _static_string(node.value, constants)
    if isinstance(node, ast.JoinedStr):
        values = [_static_string(value, constants) for value in node.values]
        return None if any(value is None for value in values) else "".join(values)
    return None


def _string_constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    changed = True
    while changed:
        changed = False
        for node in assignments:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            value = _static_string(node.value, constants)
            if value is not None and constants.get(targets[0].id) != value:
                constants[targets[0].id] = value
                changed = True
    return constants


def _dynamic_import_findings(
    path: Path,
    tree: ast.AST,
) -> list[tuple[str, int, str]]:
    bindings = _import_bindings(tree)
    constants = _string_constants(tree)
    findings: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = _qualified_name(node.func, bindings)
        if function in {"builtins.getattr", "getattr"}:
            attribute = _static_string(
                node.args[1] if len(node.args) > 1 else None,
                constants,
            )
            if attribute in {"__import__", "import_module"}:
                findings.append(
                    (_display_path(path), node.lineno, f"<reflective:{attribute}>")
                )
            continue
        if function not in {
            "builtins.__import__",
            "importlib.import_module",
        }:
            continue
        target = _static_string(node.args[0], constants) if node.args else None
        if target is None or not _permitted_import(target):
            findings.append(
                (_display_path(path), node.lineno, target or "<dynamic>")
            )
    return findings


def _forbidden_import_findings(
    files: list[Path],
) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node, target in _resolved_imports(path, tree):
            if not _permitted_import(target):
                findings.append(
                    (_display_path(path), node.lineno, target)
                )
        findings.extend(_dynamic_import_findings(path, tree))
    return sorted(findings)


def test_transport_dependencies_are_protocol_only_and_alias_resistant() -> None:
    assert _forbidden_import_findings(_transport_files()) == []


def test_transport_rejects_freecad_qt_and_runtime_locator_dependencies() -> None:
    files = _transport_files()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_roots = {
            target.lstrip(".").partition(".")[0]
            for _node, target in _resolved_imports(path, tree)
        }
        assert not imported_roots & _FORBIDDEN_RUNTIME_ROOTS

    assert lint_python.scan_runtime_locators(files, ROOT) == []


def test_transport_is_absent_from_document_authority_censuses() -> None:
    census = authority_symbol_census(root=ROOT, production_files=_transport_files())

    assert census
    assert all(records == [] for records in census.values()), census


def test_transport_has_no_raw_architecture_findings() -> None:
    assert lint_python.scan_architecture(_transport_files(), ROOT) == []


@pytest.mark.parametrize(
    "source",
    [
        "import FreeCAD\n",
        "from ..rpc_server import rpc_server\n",
        (
            "from importlib import import_module as imported\n"
            "load = imported\n"
            "target = 'addon.FreeCADMCP.' + 'rpc_server'\n"
            "value = load(target)\n"
        ),
        (
            "from importlib import import_module as imported\n"
            "load: object = imported\n"
            "value = load('FreeCAD')\n"
        ),
        (
            "from importlib import import_module as imported\n"
            "(load,) = (imported,)\n"
            "value = load('FreeCAD')\n"
        ),
        (
            "import importlib\n"
            "load = getattr(importlib, 'import_module')\n"
            "value = load('FreeCAD')\n"
        ),
        (
            "from builtins import __import__ as imported\n"
            "load = imported\n"
            "target = f'addon.FreeCADMCP.{\"document_lock\"}'\n"
            "value = load(target)\n"
        ),
        "import importlib\nvalue = importlib.import_module(name)\n",
    ],
)
def test_transport_dependency_oracle_rejects_static_alias_and_dynamic_bypasses(
    tmp_path: Path,
    source: str,
) -> None:
    path = tmp_path / "addon" / "FreeCADMCP" / "transport" / "injected.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")

    assert _forbidden_import_findings([path])


def test_canonical_authentication_and_replay_leaves_are_exact_protocol_aliases() -> None:
    authentication = importlib.import_module(
        "addon.FreeCADMCP.transport.authentication"
    )
    replay = importlib.import_module("addon.FreeCADMCP.transport.replay")
    session_manager = importlib.import_module(
        "addon.FreeCADMCP._shared.protocol.session_manager"
    )
    profile_secret = importlib.import_module(
        "addon.FreeCADMCP._shared.protocol.profile_secret"
    )
    manifest = importlib.import_module("addon.FreeCADMCP._shared.protocol.manifest")
    replay_cache = importlib.import_module(
        "addon.FreeCADMCP._shared.protocol.request_replay_cache"
    )

    assert authentication.SessionManager is session_manager.SessionManager
    assert authentication.load_profile_secret is profile_secret.load_profile_secret
    assert authentication.make_runtime_manifest is manifest.make_runtime_manifest
    assert replay.RequestReplayCache is replay_cache.RequestReplayCache


def test_rpc_server_imports_authentication_and_replay_only_through_transport() -> None:
    tree = ast.parse(
        RPC_SERVER_PATH.read_text(encoding="utf-8"),
        filename=str(RPC_SERVER_PATH),
    )
    protected = {
        "RequestReplayCache",
        "SessionManager",
        "load_profile_secret",
        "make_runtime_manifest",
    }
    imports = Counter(
        (
            node.level,
            node.module or "",
            tuple(sorted(alias.name for alias in node.names if alias.name in protected)),
        )
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name in protected for alias in node.names)
    )

    assert imports == Counter(
        {
            (
                2,
                "transport.authentication",
                ("SessionManager", "load_profile_secret", "make_runtime_manifest"),
            ): 1,
            (2, "transport.replay", ("RequestReplayCache",)): 1,
            (
                0,
                "transport.authentication",
                ("SessionManager", "load_profile_secret", "make_runtime_manifest"),
            ): 1,
            (0, "transport.replay", ("RequestReplayCache",)): 1,
        }
    )
    assert not any(
        isinstance(node, ast.ImportFrom)
        and "_shared.protocol" in (node.module or "")
        and any(alias.name in protected for alias in node.names)
        for node in ast.walk(tree)
    )


def test_transport_canonical_leaves_import_with_freecad_and_qt_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__

    def rejecting_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        root = name.partition(".")[0]
        if root in _FORBIDDEN_RUNTIME_ROOTS:
            raise AssertionError(f"blocked dependency imported: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", rejecting_import)
    for name in (
        "addon.FreeCADMCP.transport.authentication",
        "addon.FreeCADMCP.transport.json_rpc_errors",
        "addon.FreeCADMCP.transport.json_rpc_transport",
        "addon.FreeCADMCP.transport.ip_filter",
        "addon.FreeCADMCP.transport.listener",
        "addon.FreeCADMCP.transport.request_handler",
        "addon.FreeCADMCP.transport.replay",
    ):
        sys.modules.pop(name, None)
        importlib.import_module(name)
