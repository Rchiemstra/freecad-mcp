#!/usr/bin/env python3
"""Permanent tombstones: no templates, no template_resources, no generated execution."""

from __future__ import annotations

import ast
import importlib.util
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))

from ci.check_execution_policy_contract import (  # noqa: E402
    is_cad_tool,
    scan_execution_policy_completeness,
    scan_typed_rpc_handler_names,
)
from ci.scan_execution_policy_gates import scan_op_architecture  # noqa: E402
from ci.scan_typed_feature_contract import _called_names, _paths, _try_function  # noqa: E402

_TEMPLATES_RELATIVE = "src/freecad_mcp/templates"
_TEMPLATE_RESOURCES = "freecad_mcp.template_resources"
_TEMPLATE_SYMBOLS = frozenset(
    {
        "read_template_text",
        "read_template_lines",
        "render_template_text",
        "render_template_lines",
    }
)
_GENERATED_EXECUTION = frozenset({"_run_code", "_run_json_code", "execute_code"})
_EXECUTE_CODE_CARVEOUTS = frozenset({"execute_code", "execute_code_async"})
_LEGACY_IMPORT_CARVEOUTS = frozenset(
    {
        "telemetry.legacy_parser",
        "freecad_mcp.telemetry.legacy_parser",
        "capabilities.legacy_shims",
        "freecad_mcp.capabilities.legacy_shims",
        "operations.legacy_locking_deprecations",
        "freecad_mcp.operations.legacy_locking_deprecations",
        "save_legacy",
    }
)
_SCANNER_RELATIVE = "ci/check_template_tombstone_contract.py"
_TOMBSTONE_TEST_RELATIVE = "tests/architecture/test_template_tombstones.py"
_PUBLIC_ADAPTER_OVERRIDES = {
    "body_create": "src/freecad_mcp/operations/parametric_ops/body_ops.py",
}
_ARCHITECTURE_GOLDEN_OPS = (
    "body_create",
    "boolean_union",
    "close_document",
    "bounding_box",
    "undo",
    "redo",
    "export_step",
    "set_color",
    "sketch_offset",
    "measure_distance",
    "get_document_tree",
    "diagnose_pocket",
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _scan_roots(root: Path) -> tuple[Path, ...]:
    return tuple(
        path
        for path in (
            root / "src",
            root / "addon",
            root / "tests",
            root / "ci",
        )
        if path.is_dir()
    )


def _should_skip_template_scan(relative: str) -> bool:
    return relative in {_SCANNER_RELATIVE, _TOMBSTONE_TEST_RELATIVE}


def _module_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import):
        return None
    if isinstance(node, ast.ImportFrom):
        if node.module is None:
            return None
        return node.module
    return None


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = _module_name(node)
            if module is not None:
                modules.append(module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if module is None:
                    modules.append(alias.name)
                else:
                    modules.append(f"{module}.{alias.name}")
    return modules


def _iter_python_sources(
    root: Path,
    overrides: Mapping[str, str],
) -> list[tuple[str, str]]:
    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for scan_root in _scan_roots(root):
        for path in sorted(scan_root.rglob("*.py")):
            relative = _relative(root, path)
            if relative in seen or _should_skip_template_scan(relative):
                continue
            seen.add(relative)
            items.append((relative, overrides.get(relative, path.read_text(encoding="utf-8"))))
    for relative, source in sorted(overrides.items()):
        if relative in seen or _should_skip_template_scan(relative):
            continue
        if not relative.endswith(".py"):
            continue
        prefix = relative.split("/", 1)[0]
        if prefix not in {"src", "addon", "tests", "ci"}:
            continue
        seen.add(relative)
        items.append((relative, source))
    return items


def _scan_template_resource_usage(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    overrides = source_overrides or {}
    violations: list[str] = []
    for relative, source in _iter_python_sources(root, overrides):
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == _TEMPLATE_RESOURCES or alias.name.endswith(
                        ".template_resources"
                    ):
                        violations.append(
                            f"template tombstone: {relative} imports template_resources"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module in {_TEMPLATE_RESOURCES, "template_resources"}:
                    violations.append(
                        f"template tombstone: {relative} imports template_resources"
                    )
                for alias in node.names:
                    if alias.name in _TEMPLATE_SYMBOLS:
                        violations.append(
                            f"template tombstone: {relative} imports {alias.name}"
                        )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in _TEMPLATE_SYMBOLS:
                    violations.append(
                        f"template tombstone: {relative} calls {node.func.id}"
                    )
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in _TEMPLATE_SYMBOLS
                ):
                    violations.append(
                        f"template tombstone: {relative} calls {node.func.attr}"
                    )
    return sorted(set(violations))


def _cad_tool_entries(root: Path) -> list[tuple[str, str | None]]:
    from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

    bootstrap_unit_test_runtime()
    from freecad_mcp.capabilities.load import all_subject_manifests

    entries: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for manifest in all_subject_manifests():
        for entry in manifest.tools:
            if not is_cad_tool(entry):
                continue
            if entry.name in seen:
                continue
            seen.add(entry.name)
            entries.append((entry.name, entry.register_module))
    return entries


def _register_module_path(root: Path, register_module: str | None) -> Path | None:
    if register_module is None:
        return None
    generated = (
        root / "src/freecad_mcp/generated/capabilities/register_modules" / f"{register_module}.py"
    )
    if generated.is_file():
        return generated
    direct = root / "src/freecad_mcp" / f"{register_module}.py"
    if direct.is_file():
        return direct
    return None


def _public_adapter_path(root: Path, op: str) -> Path | None:
    override = _PUBLIC_ADAPTER_OVERRIDES.get(op)
    if override is not None:
        path = root / override
        if path.is_file():
            return path
    path = root / _paths(op)["public"]
    return path if path.is_file() else None


def _addon_leaf_path(root: Path, op: str) -> Path | None:
    path = root / _paths(op)["leaf"]
    return path if path.is_file() else None


def _scan_function_calls(source: str, relative: str, function_name: str) -> set[str]:
    tree = ast.parse(source, filename=relative)
    function = _try_function(tree, function_name)
    if function is None:
        return set()
    return set(_called_names(function))


def _scan_generated_execution(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    overrides = source_overrides or {}
    violations: list[str] = []
    for op, register_module in _cad_tool_entries(root):
        if op in _EXECUTE_CODE_CARVEOUTS:
            continue
        surfaces: list[tuple[str, str, str]] = []
        public_path = _public_adapter_path(root, op)
        if public_path is not None:
            relative = _relative(root, public_path)
            surfaces.append(
                (
                    relative,
                    f"{op}_operation",
                    overrides.get(relative, public_path.read_text(encoding="utf-8")),
                )
            )
        leaf_path = _addon_leaf_path(root, op)
        if leaf_path is not None:
            relative = _relative(root, leaf_path)
            surfaces.append(
                (
                    relative,
                    f"run_{op}",
                    overrides.get(relative, leaf_path.read_text(encoding="utf-8")),
                )
            )
        register_path = _register_module_path(root, register_module)
        if register_path is not None:
            relative = _relative(root, register_path)
            surfaces.append(
                (
                    relative,
                    f"_register_{op}",
                    overrides.get(relative, register_path.read_text(encoding="utf-8")),
                )
            )
        for relative, function_name, source in surfaces:
            hits = sorted(
                _GENERATED_EXECUTION
                & _scan_function_calls(source, relative, function_name)
            )
            if hits:
                violations.append(
                    f"template tombstone: CAD {op} {function_name} calls generated execution "
                    f"({', '.join(hits)}) in {relative}"
                )
    return violations


def _legacy_module_violation(module: str) -> bool:
    if not module.endswith("_legacy"):
        return False
    normalized = module.removeprefix("freecad_mcp.")
    if normalized in _LEGACY_IMPORT_CARVEOUTS or module in _LEGACY_IMPORT_CARVEOUTS:
        return False
    if normalized.endswith("save_legacy") or module.endswith("save_legacy"):
        return False
    return True


def _scan_legacy_imports(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    overrides = source_overrides or {}
    violations: list[str] = []
    for op, register_module in _cad_tool_entries(root):
        if op in _EXECUTE_CODE_CARVEOUTS:
            continue
        paths: list[tuple[str, Path]] = []
        public_path = _public_adapter_path(root, op)
        if public_path is not None:
            paths.append(("public adapter", public_path))
        leaf_path = _addon_leaf_path(root, op)
        if leaf_path is not None:
            paths.append(("addon leaf", leaf_path))
        register_path = _register_module_path(root, register_module)
        if register_path is not None:
            paths.append(("register module", register_path))
        for label, path in paths:
            relative = _relative(root, path)
            source = overrides.get(relative, path.read_text(encoding="utf-8"))
            tree = ast.parse(source, filename=relative)
            for module in _imported_modules(tree):
                if _legacy_module_violation(module):
                    violations.append(
                        f"template tombstone: CAD {op} {label} imports legacy module {module} "
                        f"({relative})"
                    )
    return violations


def scan_templates_directory(root: Path) -> list[str]:
    templates_path = root / _TEMPLATES_RELATIVE
    if templates_path.exists():
        return [f"template tombstone: {_TEMPLATES_RELATIVE} must not exist"]
    return []


def scan_template_tombstones(
    root: Path,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    """Return stable violations for permanent template and generated-execution tombstones."""

    overrides = source_overrides or {}
    violations: list[str] = []
    violations.extend(scan_templates_directory(root))

    violations.extend(_scan_template_resource_usage(root, source_overrides=overrides))
    violations.extend(_scan_generated_execution(root, source_overrides=overrides))
    violations.extend(_scan_legacy_imports(root, source_overrides=overrides))
    violations.extend(scan_execution_policy_completeness(root))

    for op in _ARCHITECTURE_GOLDEN_OPS:
        try:
            violations.extend(scan_op_architecture(root, op, source_overrides=overrides))
        except ValueError as exc:
            violations.append(
                f"template tombstone: architecture gate failed for {op}: {exc}"
            )

    return violations


def _freecad_mcp_distributions():
    from importlib.metadata import PackageNotFoundError, distribution

    seen: set[str] = set()
    for package_name in ("freecad-mcp", "freecad_mcp"):
        try:
            dist = distribution(package_name)
        except PackageNotFoundError:
            continue
        if dist.metadata["Name"] in seen:
            continue
        seen.add(dist.metadata["Name"])
        yield dist


def _distribution_template_violations(dist) -> list[str]:
    violations: list[str] = []
    files = dist.files
    if files is None:
        return violations
    for entry in files:
        parts = entry.parts
        if "templates" in parts:
            violations.append(
                "template tombstone: installed package distribution "
                f"{dist.metadata['Name']} ships templates at {entry.as_posix()}"
            )
        if any(part == "template_resources" for part in parts):
            violations.append(
                "template tombstone: installed package distribution "
                f"{dist.metadata['Name']} ships template_resources at {entry.as_posix()}"
            )
    return violations


def _installed_package_template_violations() -> list[str]:
    violations: list[str] = []
    distributions = list(_freecad_mcp_distributions())
    for dist in distributions:
        violations.extend(_distribution_template_violations(dist))

    try:
        import freecad_mcp
    except ModuleNotFoundError:
        return violations

    package_file = Path(freecad_mcp.__file__).resolve()
    package_dir = package_file.parent
    templates_dir = package_dir / "templates"
    if templates_dir.exists():
        violations.append(
            "template tombstone: installed package contains templates directory "
            f"at {templates_dir}"
        )
    if importlib.util.find_spec(_TEMPLATE_RESOURCES) is not None:
        violations.append(
            "template tombstone: installed package still exposes "
            "freecad_mcp.template_resources"
        )
    return violations


def scan_installed_package_tombstones() -> list[str]:
    """Fail if an installed freecad_mcp wheel still ships templates or template_resources."""

    src_path = _ROOT / "src"
    src_path_str = str(src_path)
    src_resolved = src_path.resolve()
    original_path = list(sys.path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "freecad_mcp" or name.startswith("freecad_mcp.")
    }

    filtered_path: list[str] = []
    for entry in sys.path:
        if entry == src_path_str:
            continue
        try:
            if Path(entry).resolve() == src_resolved:
                continue
        except OSError:
            pass
        filtered_path.append(entry)
    sys.path[:] = filtered_path

    for name in original_modules:
        del sys.modules[name]

    try:
        return _installed_package_template_violations()
    finally:
        sys.path[:] = original_path
        for name, module in original_modules.items():
            sys.modules[name] = module


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path(__file__).resolve().parents[1]
    violations = scan_template_tombstones(root)
    violations.extend(scan_installed_package_tombstones())
    for violation in violations:
        print(violation, file=sys.stderr)
    if violations:
        return 1
    print(
        "template tombstone contract: OK "
        f"({len(scan_typed_rpc_handler_names(root))} typed RPC handlers; "
        "no templates; no template_resources; no generated execution)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
