#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff>=0.9"]
# ///
"""Run common Ruff checks and strict module-size checks.

ARCH001 limits every checked Python file to 300 physical lines.
ARCH002 limits every checked Python file to one class declaration. Nested
classes, dataclasses, enums, protocols, and exceptions all count.

Run from the repository root:
    uv run lint_python.py
    uv run lint_python.py src addon tests
    uv run lint_python.py --fix
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import shutil
import subprocess
import sys
import tokenize
from collections.abc import Sequence
from pathlib import Path

MAX_LINES = 300
MAX_CLASSES = 1
LINE_LENGTH = 100
TARGET_VERSION = "py311"
RUFF_RULES = ("E", "F", "I", "UP", "B", "SIM", "C901", "RUF")
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
Violation = tuple[str, int, int, str, str]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ruff plus 300-line and one-class-per-file checks."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to check; default is the current directory.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=MAX_LINES,
        help=f"Maximum physical lines per file; default {MAX_LINES}.",
    )
    parser.add_argument(
        "--max-classes",
        type=int,
        default=MAX_CLASSES,
        help=f"Maximum class declarations per file; default {MAX_CLASSES}.",
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
        help="Skip Ruff and run only ARCH001 and ARCH002.",
    )
    args = parser.parse_args(argv)
    if args.max_lines < 1:
        parser.error("--max-lines must be at least 1")
    if args.max_classes < 0:
        parser.error("--max-classes must be zero or greater")
    return args


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


def check_architecture(
    path: Path, root: Path, max_lines: int, max_classes: int
) -> list[Violation]:
    display = display_path(path, root)
    try:
        source = read_source(path)
    except (OSError, SyntaxError, UnicodeError) as exc:
        return [(display, 1, 1, "ARCH000", f"cannot read source: {exc}")]

    violations: list[Violation] = []
    line_count = len(source.splitlines())
    if line_count > max_lines:
        violations.append(
            (
                display,
                max_lines + 1,
                1,
                "ARCH001",
                f"file has {line_count} physical lines; maximum is {max_lines}",
            )
        )
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        violations.append(
            (
                display,
                int(exc.lineno or 1),
                int(exc.offset or 1),
                "ARCH000",
                f"cannot parse source: {exc.msg}",
            )
        )
        return violations

    classes = sorted(
        (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    if len(classes) > max_classes:
        extra = classes[max_classes]
        names = ", ".join(f"{node.name}@{node.lineno}" for node in classes)
        violations.append(
            (
                display,
                extra.lineno,
                extra.col_offset + 1,
                "ARCH002",
                f"file declares {len(classes)} classes; maximum is {max_classes}: {names}",
            )
        )
    return violations


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
            "lint: Ruff is unavailable. Use 'uv run lint_python.py' or "
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


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path.cwd().resolve()
    files = discover_files(args.paths, root, args.exclude)
    if not files:
        print("lint: no Python files found", file=sys.stderr)
        return 2

    print(f"lint: checking {len(files)} Python files")
    violations = [
        item
        for path in files
        for item in check_architecture(
            path, root, args.max_lines, args.max_classes
        )
    ]
    for path, line, column, code, message in sorted(violations):
        print(f"{path}:{line}:{column}: {code} {message}")

    ruff_result = 0
    if not args.architecture_only:
        ruff_result = run_ruff(files, args.fix)
    if violations or ruff_result:
        return 1 if ruff_result in {0, 1} else ruff_result
    print("lint: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
