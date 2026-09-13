"""Discover typed-RPC platform targets without per-operation list edits."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PLATFORM_FILES = (
    "addon/FreeCADMCP/collaboration_api.py",
    "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_dependencies.py",
    "addon/FreeCADMCP/rpc_server/methods/lease_methods_ops/collaboration_dependencies.py",
    "src/freecad_mcp/freecad_client.py",
    "src/freecad_mcp/freecad_client_ops/freecad_connection.py",
)

_MYPY_GLOBS = (
    "addon/FreeCADMCP/_shared/protocol/*_contract.py",
    "src/freecad_mcp/_shared/protocol/*_contract.py",
    "tests/typecheck/*_protocol.py",
)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _mutation_paths_for_op(ops_dir: Path, op_stem: str) -> list[Path]:
    candidates = [ops_dir / f"{op_stem}_mutation.py"]
    if op_stem == "body_create":
        candidates.append(ops_dir / "body_mutation.py")
    return [path for path in candidates if path.is_file()]


def _client_op_paths(client_dir: Path, op_stem: str) -> list[Path]:
    candidates = [client_dir / f"{op_stem}.py"]
    if op_stem == "body_create":
        candidates.append(client_dir / "body_ops.py")
    return [path for path in candidates if path.is_file()]


def _iter_contract_ops(root: Path) -> list[str]:
    contract_dir = root / "src/freecad_mcp/_shared/protocol"
    return sorted(
        contract.stem.removesuffix("_contract")
        for contract in contract_dir.glob("*_contract.py")
    )


def discover_typed_mypy_files(root: Path) -> list[str]:
    """Return mypy entrypoints plus contract-paired modules reachable by import."""

    files: set[str] = set(_PLATFORM_FILES)
    for pattern in _MYPY_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                files.add(_relative(root, path))

    ops_dir = root / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops"
    client_dir = root / "src/freecad_mcp/operations/parametric_ops"
    for op_stem in _iter_contract_ops(root):
        leaf = ops_dir / f"{op_stem}.py"
        if leaf.is_file():
            files.add(_relative(root, leaf))
        for mutation in _mutation_paths_for_op(ops_dir, op_stem):
            files.add(_relative(root, mutation))
        for client_op in _client_op_paths(client_dir, op_stem):
            files.add(_relative(root, client_op))

    return sorted(files)


def run_discovered_mypy(root: Path) -> int:
    """Typecheck the typed slice using the static ``pyproject.toml`` editor config."""

    return subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental"],
        cwd=root,
        check=False,
    ).returncode


def discover_contract_check_scripts(root: Path) -> list[Path]:
    """Return every ``ci/check_*_contract.py`` gate script."""

    return sorted(root.glob("ci/check_*_contract.py"))
