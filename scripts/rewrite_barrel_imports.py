#!/usr/bin/env python3
"""Rewrite ARCH104 barrel imports to import symbols from defining leaf modules."""

from __future__ import annotations

import argparse
import ast
import tokenize
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _leaf_for_symbol(package_dir: Path, symbol: str) -> str | None:
    init_path = package_dir / "__init__.py"
    if not init_path.is_file():
        return None
    tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        for alias in node.names:
            exported = alias.asname or alias.name
            if exported == symbol:
                return node.module.lstrip(".")
    return None


def _package_dir_for_import(file_path: Path, node: ast.ImportFrom) -> Path | None:
    directory = file_path.parent
    for _ in range(max(0, (node.level or 0) - 1)):
        directory = directory.parent
    if node.module:
        directory = directory.joinpath(*node.module.split("."))
    if not (directory / "__init__.py").is_file():
        return None
    if (directory.with_suffix(".py")).is_file():
        return None
    return directory


def _rewrite_node(source: str, file_path: Path, node: ast.ImportFrom) -> tuple[str, bool]:
    package_dir = _package_dir_for_import(file_path, node)
    if package_dir is None:
        return source, False

    leaf_by_symbol: dict[str, str | None] = {
        alias.name: _leaf_for_symbol(package_dir, alias.asname or alias.name)
        for alias in node.names
    }
    if not any(leaf_by_symbol.values()):
        return source, False

    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = (node.end_lineno or node.lineno) - 1
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    prefix = "." * (node.level or 0)
    base_module = node.module or ""

    new_lines: list[str] = []
    for alias in node.names:
        symbol = alias.asname or alias.name
        leaf = leaf_by_symbol[alias.name]
        asname = f" as {alias.asname}" if alias.asname and alias.asname != alias.name else ""
        if leaf is None:
            module_path = f"{prefix}{base_module}" if base_module else prefix
            new_lines.append(
                f"{indent}from {module_path} import {alias.name}{asname}\n"
            )
            continue
        if base_module:
            module_path = f"{prefix}{base_module}.{leaf}"
        else:
            module_path = f"{prefix}{leaf}"
        new_lines.append(f"{indent}from {module_path} import {alias.name}{asname}\n")

    lines[start : end + 1] = new_lines
    return "".join(lines), True


def rewrite_file(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    changed = False
    while True:
        tree = ast.parse(source, filename=str(path))
        updated = False
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue
            source, node_changed = _rewrite_node(source, path, node)
            if node_changed:
                changed = True
                updated = True
                break
        if not updated:
            break
    if changed:
        path.write_text(source, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    targets: list[Path] = []
    for raw in args.paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.is_file():
            targets.append(candidate)
        else:
            targets.extend(sorted(candidate.rglob("*.py")))

    count = 0
    for path in targets:
        if any(part in path.parts for part in ("generated", "architecture_policy_fixtures")):
            continue
        if rewrite_file(path):
            print(path.relative_to(ROOT))
            count += 1
    print(f"rewrote {count} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
