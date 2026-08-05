"""Structural boundaries for the inert add-on runtime container."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

from ci import lint_python
from tests.helpers.architecture_authority import authority_symbol_census

ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = ROOT / "addon" / "FreeCADMCP"
RUNTIME_PATH = ADDON_ROOT / "runtime.py"
FORBIDDEN_AUTHORITY_STEMS = frozenset(
    {
        "authorit",
        "checkpoint",
        "conflict",
        "credential",
        "dirt",
        "document",
        "epoch",
        "heartbeat",
        "journal",
        "leas",
        "lifecycle",
        "lock",
        "mutation",
        "persist",
        "policy",
        "recover",
        "revision",
        "restor",
        "rollback",
        "sav",
        "sidecar",
        "snapshot",
        "store",
        "writer",
    }
)
ALLOWED_INFRASTRUCTURE_IDENTIFIERS = frozenset({"Lock", "_dispose_lock"})
FORBIDDEN_IMPORT_MACHINERY = frozenset(
    {"__builtins__", "__import__", "builtins", "import_module", "importlib"}
)

pytestmark = pytest.mark.unit


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _import_root(node: ast.Import | ast.ImportFrom) -> str | None:
    if isinstance(node, ast.Import):
        return None
    if node.level:
        return ""
    return (node.module or "").partition(".")[0]


def _dynamic_import_names(tree: ast.AST) -> set[str]:
    names = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"builtins", "importlib"}:
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name in {"__import__", "import_module"}
            )
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            value = node.value
            if not isinstance(target, ast.Name):
                continue
            is_alias = isinstance(value, ast.Name) and value.id in names
            is_alias = is_alias or (
                isinstance(value, ast.Attribute)
                and value.attr in {"__import__", "import_module"}
            )
            if is_alias and target.id not in names:
                names.add(target.id)
                changed = True
    return names


def _is_dynamic_import_call(node: ast.Call, names: set[str]) -> bool:
    return (
        isinstance(node.func, ast.Name) and node.func.id in names
    ) or (
        isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
    )


def _literal_dynamic_imports(tree: ast.AST) -> list[ast.Call]:
    findings: list[ast.Call] = []
    names = _dynamic_import_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if (
            _is_dynamic_import_call(node, names)
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            findings.append(node)
    return findings


def _static_string(
    node: ast.AST,
    constants: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left, constants)
        right = _static_string(node.right, constants)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts = [
            _static_string(value, constants)
            for value in node.values
        ]
        return None if any(part is None for part in parts) else "".join(parts)
    if isinstance(node, ast.FormattedValue):
        return _static_string(node.value, constants)
    return None


def _string_constants(tree: ast.AST) -> dict[str, str]:
    constants: dict[str, str] = {}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            value = _static_string(node.value, constants) if node.value else None
            if value is not None and targets[0].id not in constants:
                constants[targets[0].id] = value
                changed = True
    return constants


def _identifier_words(identifier: str) -> set[str]:
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", identifier)
    return {
        word.lower()
        for word in re.split(r"[^A-Za-z0-9]+", camel_split)
        if word
    }


def _forbidden_stems(identifier: str) -> list[str]:
    if identifier in ALLOWED_INFRASTRUCTURE_IDENTIFIERS:
        return []
    words = _identifier_words(identifier)
    return sorted(
        stem
        for stem in FORBIDDEN_AUTHORITY_STEMS
        if any(word.startswith(stem) for word in words)
    )


def _named_identifiers(tree: ast.AST) -> list[tuple[ast.AST, str]]:
    identifiers: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) | ast.Attribute(attr=name) | ast.arg(arg=name):
                identifiers.append((node, name))
            case ast.keyword(arg=name) if name is not None:
                identifiers.append((node, name))
            case ast.FunctionDef(name=name) | ast.AsyncFunctionDef(
                name=name
            ) | ast.ClassDef(name=name):
                identifiers.append((node, name))
            case ast.alias(name=name, asname=asname):
                identifiers.extend((node, part) for part in name.split("."))
                if asname:
                    identifiers.append((node, asname))
    return identifiers


def _forbidden_vocabulary(tree: ast.AST) -> list[tuple[int, str, list[str]]]:
    values = list(_named_identifiers(tree))
    docstrings = {
        node.body[0].value
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    values.extend(
        (node, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node not in docstrings
    )
    return [
        (getattr(node, "lineno", 0), value, forbidden)
        for node, value in values
        if (forbidden := _forbidden_stems(value))
    ]


def _import_machinery_findings(tree: ast.AST) -> list[tuple[int, str]]:
    return [
        (getattr(node, "lineno", 0), value)
        for node, value in _named_identifiers(tree)
        if value in FORBIDDEN_IMPORT_MACHINERY
    ]


def _contains_mutable_value(node: ast.AST | None) -> bool:
    if node is None:
        return False
    mutable = (
        ast.Dict,
        ast.DictComp,
        ast.List,
        ast.ListComp,
        ast.Set,
        ast.SetComp,
    )
    return any(isinstance(value, mutable) for value in ast.walk(node))


class _ImportTimeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []
        self.class_bindings: set[str] = set()
        self.mutable_values: list[ast.AST] = []
        self._class_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._class_depth:
            self.class_bindings.add(node.name)
        for expression in [
            *node.decorator_list,
            *node.bases,
            *(keyword.value for keyword in node.keywords),
        ]:
            self.visit(expression)
        self._class_depth += 1
        for statement in node.body:
            self.visit(statement)
        self._class_depth -= 1

    def _visit_function_definition(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        expressions = [
            *node.decorator_list,
            *node.args.defaults,
            *(default for default in node.args.kw_defaults if default is not None),
        ]
        self.mutable_values.extend(
            expression
            for expression in expressions
            if _contains_mutable_value(expression)
        )
        for expression in expressions:
            self.visit(expression)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._class_depth:
            self.class_bindings.add(node.name)
        self._visit_function_definition(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._class_depth:
            self.class_bindings.add(node.name)
        self._visit_function_definition(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._class_depth:
            self.class_bindings.update(
                name
                for target in node.targets
                for name in _bound_names(target)
            )
        if self._class_depth and _contains_mutable_value(node.value):
            self.mutable_values.append(node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._class_depth:
            self.class_bindings.update(_bound_names(node.target))
        if self._class_depth and _contains_mutable_value(node.value):
            self.mutable_values.append(node.value)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        if self._class_depth:
            self.class_bindings.update(
                alias.asname or alias.name.partition(".")[0]
                for alias in node.names
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._class_depth:
            self.class_bindings.update(
                alias.asname or alias.name for alias in node.names
            )


def _bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, (ast.List, ast.Tuple)):
        return {name for element in node.elts for name in _bound_names(element)}
    return set()


def _import_time_state(tree: ast.Module) -> _ImportTimeVisitor:
    visitor = _ImportTimeVisitor()
    visitor.visit(tree)
    return visitor


def _import_time_calls(tree: ast.Module) -> list[ast.Call]:
    return _import_time_state(tree).calls


def _trusted_import_time_bindings(
    tree: ast.Module,
) -> frozenset[str]:
    expected = {"dataclass": "_dataclass", "field": "_field"}
    bindings: dict[str, list[tuple[str, str]]] = {}

    def record(bound: str, source: str, original: str) -> None:
        bindings.setdefault(bound, []).append((source, original))

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                record(alias.asname or alias.name.partition(".")[0], "import", alias.name)
        elif isinstance(statement, ast.ImportFrom):
            source = statement.module or ""
            for alias in statement.names:
                record(alias.asname or alias.name, source, alias.name)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    record(target.id, "assignment", target.id)
        elif isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            record(statement.target.id, "assignment", statement.target.id)
        elif isinstance(
            statement,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            record(statement.name, "definition", statement.name)

    return frozenset(
        alias
        for name, alias in expected.items()
        if bindings.get(alias) == [("dataclasses", name)]
    )


def _allowed_import_time_call(
    node: ast.Call,
    trusted: frozenset[str],
) -> bool:
    return isinstance(node.func, ast.Name) and node.func.id in trusted


def _static_all_value(node: ast.Assign | ast.AnnAssign) -> ast.AST | None:
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1:
            return None
        target = node.targets[0]
    else:
        target = node.target
    if not isinstance(target, ast.Name) or target.id != "__all__":
        return None
    value = node.value
    if not isinstance(value, (ast.List, ast.Tuple)):
        return None
    if not all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in value.elts
    ):
        return None
    return value


def _imports_gateway_runtime(tree: ast.AST) -> list[ast.AST]:
    findings: list[ast.AST] = []
    dynamic_import_names = _dynamic_import_names(tree)
    constants = _string_constants(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[-1] == "runtime" for alias in node.names
        ):
            findings.append(node)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports_module = module.split(".")[-1:] == ["runtime"]
            imports_member = any(alias.name == "runtime" for alias in node.names)
            if imports_module or imports_member:
                findings.append(node)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and _is_dynamic_import_call(node, dynamic_import_names)
        ):
            target = _static_string(node.args[0], constants)
            if target is not None and target.strip(".").split(".")[-1] == "runtime":
                findings.append(node)
    return findings


def test_gateway_runtime_imports_only_the_standard_library() -> None:
    tree = _parse(RUNTIME_PATH)
    imports = [
        node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    import_roots = {
        alias.name.partition(".")[0]
        for node in imports
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    import_roots.update(
        root for node in imports if (root := _import_root(node)) is not None
    )

    assert "" not in import_roots, "runtime.py must not use relative imports"
    assert import_roots <= sys.stdlib_module_names
    assert _literal_dynamic_imports(tree) == []
    assert _import_machinery_findings(tree) == []


def test_gateway_runtime_identifiers_have_no_document_authority_vocabulary() -> None:
    tree = _parse(RUNTIME_PATH)
    assert _forbidden_vocabulary(tree) == []


def test_gateway_runtime_is_absent_from_every_authority_census() -> None:
    census = authority_symbol_census(root=ROOT, production_files=[RUNTIME_PATH])

    assert census
    assert all(records == [] for records in census.values()), census


def test_gateway_runtime_module_body_is_inert_and_has_no_global_state() -> None:
    tree = _parse(RUNTIME_PATH)
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(
        body[0].value, ast.Constant
    ) and isinstance(body[0].value.value, str):
        body.pop(0)

    all_assignments = [
        node
        for node in body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and _static_all_value(node) is not None
    ]
    assert len(all_assignments) == 1
    assert all(
        isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
                ast.Assign,
                ast.AnnAssign,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        )
        and (
            not isinstance(node, (ast.Assign, ast.AnnAssign))
            or _static_all_value(node) is not None
        )
        for node in body
    ), [type(node).__name__ for node in body]
    assert not any(isinstance(node, ast.Global) for node in ast.walk(tree))
    import_time_state = _import_time_state(tree)
    trusted = _trusted_import_time_bindings(tree)
    assert trusted == frozenset({"_dataclass", "_field"})
    assert all(
        _allowed_import_time_call(call, trusted)
        for call in import_time_state.calls
    )
    assert not import_time_state.class_bindings & trusted
    assert import_time_state.mutable_values == []


def test_only_server_lifecycle_imports_private_gateway_runtime_builder() -> None:
    importers: list[tuple[str, ast.AST]] = []
    for path in sorted(ADDON_ROOT.rglob("*.py")):
        if path == RUNTIME_PATH:
            continue
        findings = _imports_gateway_runtime(_parse(path))
        importers.extend(
            (path.relative_to(ROOT).as_posix(), node) for node in findings
        )

    expected_path = "addon/FreeCADMCP/rpc_server/server_lifecycle.py"
    assert importers
    assert {path for path, _node in importers} == {expected_path}

    lifecycle_tree = _parse(ROOT / expected_path)
    parents = {
        child: parent
        for parent in ast.walk(lifecycle_tree)
        for child in ast.iter_child_nodes(parent)
    }
    def enclosing_function(node: ast.AST) -> str | None:
        current = parents.get(node)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
            current = parents.get(current)
        return None

    lifecycle_importers = _imports_gateway_runtime(lifecycle_tree)
    assert lifecycle_importers
    for node in lifecycle_importers:
        assert isinstance(node, ast.ImportFrom)
        assert node.module == "runtime"
        assert [(alias.name, alias.asname) for alias in node.names] == [
            ("_build_addon_runtime", None)
        ]
        assert enclosing_function(node) == "start_rpc_server"


def test_gateway_runtime_has_no_raw_architecture_findings() -> None:
    assert lint_python.scan_architecture([RUNTIME_PATH], ROOT) == []


@pytest.mark.parametrize(
    "source",
    [
        "from builtins import __import__ as load\ndef f(): return load('x')\n",
        "import importlib as machinery\ndef f(): return machinery.import_module('x')\n",
        "def f(): return __import__('x')\n",
    ],
)
def test_import_machinery_oracle_rejects_aliases_and_computed_targets(
    source: str,
) -> None:
    assert _import_machinery_findings(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        (
            "from builtins import __import__ as load\n"
            "value = load('addon.FreeCADMCP.' + 'runtime')\n"
        ),
        (
            "from importlib import import_module as imported\n"
            "load = imported\n"
            "target = f'addon.FreeCADMCP.{\"runtime\"}'\n"
            "value = load(target)\n"
        ),
        (
            "import importlib as machinery\n"
            "load = machinery.import_module\n"
            "target = 'addon.FreeCADMCP.runtime'\n"
            "value = load(target)\n"
        ),
    ],
)
def test_runtime_importer_oracle_rejects_alias_and_computed_targets(
    source: str,
) -> None:
    assert _imports_gateway_runtime(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        "@trigger()\nclass AddonRuntime: pass\n",
        "class AddonRuntime(factory()): pass\n",
        "def create(value=trigger()): pass\n",
        "class AddonRuntime:\n    active = trigger()\n",
        "class AddonRuntime:\n    trigger()\n",
        "class AddonRuntime:\n    if enabled:\n        trigger()\n",
        "class AddonRuntime:\n    value: object = _field(default_factory=trigger())\n",
    ],
)
def test_inert_body_oracle_rejects_hidden_import_time_calls(source: str) -> None:
    calls = _import_time_calls(ast.parse(source))
    assert calls
    assert not all(_allowed_import_time_call(call, frozenset()) for call in calls)


def test_import_time_oracle_rejects_shadowed_trusted_helpers() -> None:
    tree = ast.parse(
        "from dataclasses import field as _field\n"
        "def _field(*args, **kwargs): return trigger()\n"
        "class AddonRuntime:\n"
        "    state: object = _field()\n"
    )

    assert "_field" not in _trusted_import_time_bindings(tree)
    assert not all(
        _allowed_import_time_call(call, _trusted_import_time_bindings(tree))
        for call in _import_time_calls(tree)
    )

    import_shadow = ast.parse(
        "from dataclasses import field as _field\n"
        "from threading import Event as _field\n"
        "class AddonRuntime:\n"
        "    state: object = _field()\n"
    )
    assert "_field" not in _trusted_import_time_bindings(import_shadow)
    assert not all(
        _allowed_import_time_call(
            call,
            _trusted_import_time_bindings(import_shadow),
        )
        for call in _import_time_calls(import_shadow)
    )

    class_import_shadow = ast.parse(
        "from dataclasses import field as _field\n"
        "class AddonRuntime:\n"
        "    from threading import Event as _field\n"
        "    state: object = _field()\n"
    )
    class_state = _import_time_state(class_import_shadow)
    assert "_field" in class_state.class_bindings


@pytest.mark.parametrize(
    "source",
    [
        "class AddonRuntime:\n    state = []\n",
        "class AddonRuntime:\n    if enabled:\n        state = {}\n",
        "class AddonRuntime:\n    def create(value={1}): pass\n",
        "def create(value=[]): pass\n",
    ],
)
def test_inert_body_oracle_rejects_mutable_class_and_default_state(
    source: str,
) -> None:
    assert _import_time_state(ast.parse(source)).mutable_values


@pytest.mark.parametrize(
    "source",
    [
        "mutation_owner: object\n",
        "lock_registry: object\n",
        "revision_writer: object\n",
        "checkpoint_policy: object\n",
        "journal_store: object\n",
        "value: 'lifecycle_epoch'\n",
        "KEY = 'sidecar_authority'\n",
    ],
)
def test_authority_vocabulary_oracle_rejects_alternate_and_string_forms(
    source: str,
) -> None:
    assert _forbidden_vocabulary(ast.parse(source))
