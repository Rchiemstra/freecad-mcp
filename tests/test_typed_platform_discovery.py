"""Unit tests for typed-RPC platform discovery gates."""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.methods import cad_methods
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_rpc_discovery import (
    discover_typed_rpc_handlers,
)
from ci.discover_typed_slice import (
    discover_contract_check_scripts,
    discover_typed_mypy_files,
    run_discovered_mypy,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

_STATIC_MYPY_PYPROJECT = textwrap.dedent(
    """\
    [tool.mypy]
    python_version = "3.12"
    strict = true
    explicit_package_bases = true
    namespace_packages = true
    follow_imports = "skip"
    warn_unused_ignores = true
    mypy_path = [".", "src"]
    files = [
        "addon/FreeCADMCP/_shared/protocol/*_contract.py",
        "src/freecad_mcp/_shared/protocol/*_contract.py",
        "tests/typecheck/*_protocol.py",
    ]

    [[tool.mypy.overrides]]
    module = [
        "addon.FreeCADMCP._shared.protocol.*",
        "freecad_mcp._shared.protocol.*",
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.*",
        "freecad_mcp.operations.parametric_ops.*",
        "tests.typecheck.*",
    ]
    follow_imports = "normal"
    disallow_any_unimported = true

    [[tool.mypy.overrides]]
    module = [
        "addon.FreeCADMCP._shared.protocol.*",
        "freecad_mcp._shared.protocol.*",
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.*",
        "freecad_mcp.operations.parametric_ops.*",
    ]
    disallow_any_explicit = true

    [[tool.mypy.overrides]]
    module = [
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies",
        "addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation",
    ]
    disallow_any_explicit = false
    """
)


def _run_editor_mypy(root: Path) -> int:
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental"],
        cwd=root,
        check=False,
    ).returncode


def _write_dummy_op_tree(root: Path, *, leaf_source: str) -> None:
    ops = root / "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops"
    addon_protocol = root / "addon/FreeCADMCP/_shared/protocol"
    src_protocol = root / "src/freecad_mcp/_shared/protocol"
    typecheck = root / "tests/typecheck"
    for directory in (ops, addon_protocol, src_protocol, typecheck):
        directory.mkdir(parents=True)

    contract = "# contract\n"
    (addon_protocol / "dummy_op_contract.py").write_text(contract, encoding="utf-8")
    (src_protocol / "dummy_op_contract.py").write_text(contract, encoding="utf-8")
    (ops / "dummy_op_mutation.py").write_text("# mutation\n", encoding="utf-8")
    (ops / "dummy_op.py").write_text(leaf_source, encoding="utf-8")
    (typecheck / "dummy_op_protocol.py").write_text(
        textwrap.dedent(
            """\
            from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import dummy_op

            _ = dummy_op.value
            """
        ),
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(_STATIC_MYPY_PYPROJECT, encoding="utf-8")


def test_cad_methods_binds_discovered_body_create_handler() -> None:
    handlers = discover_typed_rpc_handlers()
    assert "body_create" in handlers
    assert cad_methods.body_create is handlers["body_create"]
    assert "body_create" in cad_methods.__all__


def test_cad_collaborators_expose_commit_native_mutation() -> None:
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
        CadCollaborators,
    )

    calls: list[tuple[str, bool]] = []

    class _API:
        def commit_compatibility_mutation(self, *args, **kwargs):
            raise AssertionError("legacy path")

        def commit_body_create_mutation(self, *args, **kwargs):
            raise AssertionError("body-only path")

        def commit_native_mutation(
            self,
            document_name,
            callback,
            postcondition,
            *,
            structural=True,
        ):
            calls.append((document_name, structural))
            return callback(object())

    collaborators = CadCollaborators(
        compatibility_api=_API(),
        freecad=object(),
        part=object(),
        sketcher=object(),
        create_object_gui=lambda: None,
        insert_part_from_library=lambda: None,
        set_object_property=lambda: None,
        serialize_object=lambda: None,
        inspect_references_gui=lambda: None,
        repair_references_gui=lambda: None,
        recompute_and_wait=lambda: None,
        run_fem_analysis=lambda: None,
        dict_to_placement=lambda: None,
        placement_to_dict=lambda: None,
        set_extrusion_symmetric=lambda: None,
        set_feature_bool=lambda: None,
        validate_document_invariants=lambda: None,
    )

    collaborators.commit_native_mutation(
        "Model",
        lambda _doc: True,
        lambda _doc: True,
        structural=False,
    )
    assert calls == [("Model", False)]


def test_facade_bindings_publish_discovered_handlers() -> None:
    from addon.FreeCADMCP.rpc_server.rpc_server_ops import facade_bindings

    class _RPC:
        pass

    facade_bindings.bind_freecad_rpc(_RPC)
    assert callable(_RPC.body_create)


def test_discover_typed_mypy_files_includes_paired_leaf_and_client_op(
    tmp_path: Path,
) -> None:
    _write_dummy_op_tree(tmp_path, leaf_source="# leaf\n")

    discovered = discover_typed_mypy_files(tmp_path)

    assert "addon/FreeCADMCP/_shared/protocol/dummy_op_contract.py" in discovered
    assert "src/freecad_mcp/_shared/protocol/dummy_op_contract.py" in discovered
    assert "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/dummy_op_mutation.py" in discovered
    assert "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/dummy_op.py" in discovered
    assert "addon/FreeCADMCP/rpc_server/methods/cad_methods_ops/cad_mutation.py" not in discovered
    assert "tests/typecheck/dummy_op_protocol.py" in discovered


def test_uv_run_mypy_passes_on_production_pyproject() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_discovered_leaf_with_any_fails_editor_mypy_without_pyproject_edits(
    tmp_path: Path,
) -> None:
    _write_dummy_op_tree(
        tmp_path,
        leaf_source=textwrap.dedent(
            """\
            from typing import Any

            value: Any = 1
            """
        ),
    )

    assert _run_editor_mypy(tmp_path) != 0


def test_discovered_leaf_without_any_passes_editor_mypy(tmp_path: Path) -> None:
    _write_dummy_op_tree(tmp_path, leaf_source="value: int = 1\n")

    assert _run_editor_mypy(tmp_path) == 0


def test_discover_contract_check_scripts_picks_up_temporary_gate(tmp_path: Path) -> None:
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir()
    (ci_dir / "check_body_create_contract.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    gate = ci_dir / "check_dummy_op_contract.py"
    gate.write_text("raise SystemExit(0)\n", encoding="utf-8")

    scripts = discover_contract_check_scripts(tmp_path)
    assert gate in scripts
    assert len(scripts) == 2


def test_run_contract_checks_fails_on_failing_dummy_gate(tmp_path: Path) -> None:
    ci_dir = tmp_path / "ci"
    ci_dir.mkdir()
    shutil.copy2(ROOT / "ci/discover_typed_slice.py", ci_dir / "discover_typed_slice.py")
    shutil.copy2(ROOT / "ci/run_contract_checks.py", ci_dir / "run_contract_checks.py")
    (ci_dir / "check_ok_contract.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (ci_dir / "check_dummy_op_contract.py").write_text("raise SystemExit(1)\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "ci/run_contract_checks.py"],
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode != 0


def test_run_contract_checks_runs_production_gates() -> None:
    scripts = discover_contract_check_scripts(ROOT)
    assert any(path.name == "check_body_create_contract.py" for path in scripts)

    result = subprocess.run(
        [sys.executable, "ci/run_contract_checks.py"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
