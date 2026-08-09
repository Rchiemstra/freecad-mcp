"""Adversarial architecture and compatibility contracts for dispatch."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from ci import lint_python
from tests.helpers.architecture_authority import authority_symbol_census

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "addon" / "FreeCADMCP"
DISPATCH_ROOT = ADDON_ROOT / "dispatch"

pytestmark = pytest.mark.unit

_FORBIDDEN_ROOTS = frozenset(
    {
        "Draft",
        "FreeCAD",
        "FreeCADGui",
        "Part",
        "PySide",
        "PySide2",
        "PySide6",
        "Qt",
        "Sketcher",
        "pivy",
    }
)


def _dispatch_files() -> list[Path]:
    files = sorted(DISPATCH_ROOT.rglob("*.py"))
    assert files
    return files


def _qualified_name(node: ast.AST, bindings: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value, bindings)
        return f"{owner}.{node.attr}" if owner else node.attr
    return ""


def _assignment_pairs(target: ast.AST, value: ast.AST) -> list[tuple[str, ast.AST]]:
    if isinstance(target, ast.Name):
        return [(target.id, value)]
    if (
        isinstance(target, (ast.Tuple, ast.List))
        and isinstance(value, (ast.Tuple, ast.List))
        and len(target.elts) == len(value.elts)
    ):
        return [
            pair
            for left, right in zip(target.elts, value.elts, strict=True)
            for pair in _assignment_pairs(left, right)
        ]
    return []


def _bindings(tree: ast.AST) -> dict[str, str]:  # noqa: C901 - AST oracle
    bindings = {
        "__import__": "builtins.__import__",
        "getattr": "builtins.getattr",
    }
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.partition(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bindings[alias.asname or alias.name] = ".".join(
                    part for part in (node.module or "", alias.name) if part
                )
        elif isinstance(node, ast.Assign):
            assignments.extend(
                pair
                for target in node.targets
                for pair in _assignment_pairs(target, node.value)
            )
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assignments.extend(_assignment_pairs(node.target, node.value))
    for _ in range(len(assignments) + 1):
        changed = False
        for target, value in assignments:
            qualified = _qualified_name(value, bindings)
            if qualified and bindings.get(target) != qualified:
                bindings[target] = qualified
                changed = True
        if not changed:
            break
    return bindings


def _string_value(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left, constants)
        right = _string_value(node.right, constants)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        pieces = [_string_value(item, constants) for item in node.values]
        return None if any(piece is None for piece in pieces) else "".join(pieces)
    if isinstance(node, ast.FormattedValue):
        return _string_value(node.value, constants)
    return None


def _constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            value = _string_value(node.value, constants)
            if value is not None and constants.get(targets[0].id) != value:
                constants[targets[0].id] = value
                changed = True
        if not changed:
            break
    return constants


def _is_permitted(target: str) -> bool:
    normalized = target.lstrip(".")
    root = normalized.partition(".")[0]
    if root in sys.stdlib_module_names or root == "__future__":
        return True
    return normalized in {"dispatch", "addon.FreeCADMCP.dispatch"} or normalized.startswith(
        ("dispatch.", "addon.FreeCADMCP.dispatch.")
    )


def _dependency_findings(path: Path) -> list[tuple[int, str]]:  # noqa: C901 - AST oracle
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bindings = _bindings(tree)
    constants = _constants(tree)
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_permitted(alias.name):
                    findings.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            target = node.module or ""
            if node.level == 0 and not _is_permitted(target):
                findings.append((node.lineno, target))
        elif isinstance(node, ast.Subscript):
            if _qualified_name(node.value, bindings) == "sys.modules":
                findings.append((node.lineno, "<sys.modules>"))
        elif isinstance(node, ast.Call):
            function = _qualified_name(node.func, bindings)
            if function in {"builtins.getattr", "getattr"}:
                attribute = _string_value(
                    node.args[1] if len(node.args) > 1 else None,
                    constants,
                )
                if attribute in {"__import__", "import_module"}:
                    findings.append((node.lineno, f"<reflective:{attribute}>"))
            elif function in {"builtins.__import__", "importlib.import_module"}:
                target = _string_value(node.args[0] if node.args else None, constants)
                if target is None or not _is_permitted(target):
                    findings.append((node.lineno, target or "<dynamic>"))
    return sorted(findings)


def test_dispatch_is_stdlib_only_authority_free_and_python_311_parseable() -> None:
    files = _dispatch_files()
    assert all(_dependency_findings(path) == [] for path in files)
    assert lint_python.scan_runtime_locators(files, ROOT) == []
    assert lint_python.scan_architecture(files, ROOT) == []
    census = authority_symbol_census(root=ROOT, production_files=files)
    assert all(records == [] for records in census.values()), census
    for path in files:
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=(3, 11),
        )


@pytest.mark.parametrize(
    "source",
    [
        "import FreeCAD\n",
        "from addon.FreeCADMCP.rpc_server import rpc_server\n",
        "import importlib\nvalue = importlib.import_module('PySide')\n",
        "from importlib import import_module as loader\nload = loader\nload('FreeCAD')\n",
        "from importlib import import_module as loader\nload: object = loader\nload('FreeCAD')\n",
        "from importlib import import_module as loader\n(load,) = (loader,)\nload('FreeCAD')\n",
        "import importlib\nload = getattr(importlib, 'import_' + 'module')\nload('FreeCAD')\n",
        "from builtins import __import__ as loader\nloader('Free' + 'CAD')\n",
        "import sys\nvalue = sys.modules['FreeCAD']\n",
    ],
)
def test_dispatch_dependency_oracle_rejects_alias_and_reflective_bypasses(
    tmp_path: Path,
    source: str,
) -> None:
    path = tmp_path / "injected.py"
    path.write_text(source, encoding="utf-8")
    assert _dependency_findings(path)


def test_dispatch_leaves_import_with_frameworks_actively_blocked() -> None:
    modules = []
    for path in _dispatch_files():
        relative = path.relative_to(ADDON_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules.append("addon.FreeCADMCP." + ".".join(parts))
    script = r'''
import builtins, importlib, sys
sys.path.insert(0, sys.argv[1])
blocked = set(sys.argv[3].split(","))
real_import = builtins.__import__
def reject(name, globals=None, locals=None, fromlist=(), level=0):
    if name.partition(".")[0] in blocked:
        raise AssertionError("blocked framework imported: " + name)
    return real_import(name, globals, locals, fromlist, level)
builtins.__import__ = reject
for name in sys.argv[2].split(","):
    importlib.import_module(name)
'''
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            script,
            str(ROOT),
            ",".join(modules),
            ",".join(sorted(_FORBIDDEN_ROOTS)),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_old_gui_and_inflight_paths_are_exact_canonical_identities() -> None:
    from addon.FreeCADMCP.dispatch import (
        CancellationToken,
        GuiDispatchError,
        GuiOutcome,
        GuiRequest,
        InflightRequestRegistry,
    )
    from addon.FreeCADMCP.dispatch.gui_submit import execute_request
    from addon.FreeCADMCP.rpc_server.gui_dispatcher import (
        GuiDispatchError as OldGuiDispatchError,
    )
    from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiOutcome as OldGuiOutcome
    from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiRequest as OldGuiRequest
    from addon.FreeCADMCP.rpc_server.gui_dispatcher_ops.gui_dispatcher_impl import (
        GuiDispatcher,
    )
    from addon.FreeCADMCP.rpc_server.gui_dispatcher_ops.submit_helpers import (
        execute_request as old_execute_request,
    )
    from addon.FreeCADMCP.rpc_server.gui_dispatcher_qt import (
        GuiDispatcher as QtGuiDispatcher,
    )
    from addon.FreeCADMCP.rpc_server.inflight_requests import (
        CancellationToken as OldCancellationToken,
    )
    from addon.FreeCADMCP.rpc_server.inflight_requests import (
        InflightRequestRegistry as OldInflightRequestRegistry,
    )

    assert GuiRequest.__module__ == "addon.FreeCADMCP.dispatch.gui_request"
    assert InflightRequestRegistry.__module__ == (
        "addon.FreeCADMCP.dispatch.inflight_request_registry"
    )
    assert OldGuiDispatchError is GuiDispatchError
    assert OldGuiOutcome is GuiOutcome
    assert OldGuiRequest is GuiRequest
    assert old_execute_request is execute_request
    assert OldCancellationToken is CancellationToken
    assert OldInflightRequestRegistry is InflightRequestRegistry
    assert GuiDispatcher is QtGuiDispatcher


def test_live_consumers_import_dispatch_defining_modules_not_legacy_facades() -> None:
    findings: list[tuple[str, int, str]] = []
    for path in sorted(ADDON_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module.endswith(("gui_dispatcher", "inflight_requests")):
                findings.append(
                    (path.relative_to(ROOT).as_posix(), node.lineno, module)
                )
    assert findings == []


def test_flat_addon_imports_resolve_the_same_dispatch_objects() -> None:
    script = r'''
import sys, types
sys.path.insert(0, sys.argv[1])
class _Signal:
    def connect(self, *_args): pass
    def emit(self): pass
class _QObject:
    def __init__(self, *_args): pass
    def thread(self): return object()
class _Slot:
    def __call__(self, function): return function
qtcore = types.ModuleType("PySide.QtCore")
qtcore.QObject = _QObject
qtcore.Signal = _Signal
qtcore.Slot = lambda: _Slot()
qtcore.QThread = types.SimpleNamespace(currentThread=lambda: object())
qtcore.QTimer = types.SimpleNamespace(singleShot=lambda *_args: None)
qtcore.Qt = types.SimpleNamespace(
    QueuedConnection=0,
    ConnectionType=types.SimpleNamespace(QueuedConnection=0),
)
qtwidgets = types.ModuleType("PySide.QtWidgets")
qtwidgets.QApplication = types.SimpleNamespace(instance=lambda: None)
pyside = types.ModuleType("PySide")
pyside.QtCore, pyside.QtWidgets = qtcore, qtwidgets
sys.modules.update({"PySide": pyside, "PySide.QtCore": qtcore, "PySide.QtWidgets": qtwidgets})
from dispatch.gui_errors import GuiDispatchError
from dispatch.gui_request import GuiRequest
from dispatch.inflight_request_registry import InflightRequestRegistry
from rpc_server.gui_dispatcher import GuiDispatchError as OldError, GuiRequest as OldRequest
from rpc_server.gui_dispatcher_ops.gui_dispatcher_impl import GuiDispatcher
from rpc_server.gui_dispatcher_qt import GuiDispatcher as QtGuiDispatcher
from rpc_server.inflight_requests import InflightRequestRegistry as OldRegistry
assert OldError is GuiDispatchError
assert OldRequest is GuiRequest
assert OldRegistry is InflightRequestRegistry
assert GuiDispatcher is QtGuiDispatcher
'''
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(ADDON_ROOT)],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_handoff_policy_uses_bounded_dispatch_storage_without_moving_authority() -> None:
    from addon.FreeCADMCP.dispatch.continuations import (
        BoundedContinuationRegistry,
        ContinuationCapacityError,
    )
    from addon.FreeCADMCP.rpc_server.handoff_continuations import (
        HandoffContinuationStore,
    )

    now = [0.0]
    store = HandoffContinuationStore(
        ttl_seconds=5.0,
        max_entries=2,
        monotonic=lambda: now[0],
    )
    first = store.begin(mcp_runtime_id="runtime", request_id="first")
    second = store.begin(mcp_runtime_id="runtime", request_id="second")
    assert isinstance(store._registry, BoundedContinuationRegistry)
    with pytest.raises(ContinuationCapacityError):
        store.begin(mcp_runtime_id="runtime", request_id="third")
    assert store.update("runtime", "first", state="failed") is first
    third = store.begin(mcp_runtime_id="runtime", request_id="third")
    assert store.get("runtime", "first") is None
    assert store.get("runtime", "second") is second
    assert store.get("runtime", "third") is third
    with pytest.raises(ValueError, match="already registered"):
        store.begin(mcp_runtime_id="runtime", request_id="second")


def test_claimable_handoff_is_capacity_protected_but_expires_at_exact_ttl() -> None:
    from addon.FreeCADMCP.dispatch.continuations import ContinuationCapacityError
    from addon.FreeCADMCP.rpc_server.handoff_continuations import (
        HandoffContinuationStore,
    )

    now = [0.0]
    store = HandoffContinuationStore(
        ttl_seconds=5.0,
        max_entries=1,
        monotonic=lambda: now[0],
    )
    entry = store.begin(mcp_runtime_id="runtime", request_id="claimable")
    assert store.update("runtime", "claimable", state="claimable") is entry
    now[0] = 4.999
    with pytest.raises(ContinuationCapacityError):
        store.begin(mcp_runtime_id="runtime", request_id="next")
    now[0] = 5.0
    next_entry = store.begin(mcp_runtime_id="runtime", request_id="next")
    assert store.get("runtime", "claimable") is None
    assert store.get("runtime", "next") is next_entry
