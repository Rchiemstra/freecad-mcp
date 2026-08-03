from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from ci import lint_python

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "architecture_policy_fixtures"
SHAPE_RULE_CODES = {
    "capability_ownership": "ARCH101",
    "cohesive_value_types": None,
    "giant_facade": "ARCH107",
    "mixed_responsibility": "ARCH107",
    "public_symbol_budget": "ARCH106",
    "ruff_c901": "C901",
    "shim_purity": "ARCH105",
}


def _codes(source_root: Path) -> set[str]:
    files = lint_python.discover_files([str(source_root)], source_root, [])
    return {finding.code for finding in lint_python.scan_architecture(files, source_root)}


def _findings(source_root: Path) -> list[lint_python.Violation]:
    files = lint_python.discover_files([str(source_root)], source_root, [])
    return lint_python.scan_architecture(files, source_root)


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    json.loads((FIXTURE_ROOT / "boundaries" / "manifest.json").read_text(encoding="utf-8"))[
        "cases"
    ],
    ids=lambda case: case["id"],
)
def test_boundary_policy_fixtures(case: dict[str, object]) -> None:
    source_root = FIXTURE_ROOT / "boundaries" / str(case["source_root"])
    findings = _findings(source_root)
    rule = str(case["rule"])

    if case["outcome"] == "pass":
        assert findings == []
        return

    matching = [finding for finding in findings if finding.code == rule]
    assert matching, findings
    for expected in case.get("violations", []):
        expected_path = str(expected["path"])
        expected_line = int(expected["line"])
        message_fragment = str(expected["message_fragment"])
        assert any(
            finding.path == expected_path
            and finding.line == expected_line
            and message_fragment in finding.message
            for finding in matching
        ), matching
        semantic_values = [
            str(expected[key])
            for key in ("import", "target", "symbol", "resolved_barrel")
            if key in expected
        ]
        semantic_values.extend(str(subject) for subject in expected.get("subjects", []))
        for value in semantic_values:
            assert any(value in finding.message for finding in matching), (value, matching)
        kind_fragments = {
            "_rpc_mod_call": "_rpc_mod",
            "sys_modules_get": "sys.modules.get",
            "importlib_import_module": "importlib.import_module",
        }
        if "kind" in expected:
            assert any(
                kind_fragments[str(expected["kind"])] in finding.message
                for finding in matching
            )
        if "subjects" in expected:
            subject_messages = [
                finding.message
                for finding in matching
                if finding.message.startswith("module owns multiple capability subjects:")
            ]
            assert len(subject_messages) == 1
            actual_subjects = {
                subject.strip()
                for subject in subject_messages[0].split(":", maxsplit=1)[1].split(",")
            }
            assert actual_subjects == set(expected["subjects"])
    assert len(matching) == len(case.get("violations", [])), matching
    assert findings == matching


@pytest.mark.unit
@pytest.mark.parametrize(
    "case",
    json.loads((FIXTURE_ROOT / "shape" / "manifest.json").read_text(encoding="utf-8"))[
        "cases"
    ],
    ids=lambda case: case["path"],
)
def test_shape_policy_fixtures(case: dict[str, object]) -> None:
    path = FIXTURE_ROOT / "shape" / str(case["path"])
    findings = lint_python.scan_architecture([path], path.parent)
    architecture_codes = {finding.code for finding in findings}
    expected = {str(code) for code in case["expect"]}

    if "C901" in expected:
        assert architecture_codes == set()
        assert "C901" in lint_python.RUFF_RULES
        result = lint_python.run_ruff_source(path, "ruff_c901_complexity.py")
        assert result.returncode == 1
        diagnostic_codes = re.findall(r": ([A-Z]+\d+) ", result.stdout)
        assert diagnostic_codes == ["C901"], result.stdout
    else:
        assert architecture_codes == expected
        if message_fragment := case.get("message_fragment"):
            assert any(str(message_fragment) in finding.message for finding in findings)
    assert case["verdict"] in {"pass", "fail"}
    assert bool(expected) == (case["verdict"] == "fail")
    assert case["rules"]
    assert set(case["rules"]) <= SHAPE_RULE_CODES.keys()
    if case["verdict"] == "fail":
        mapped_codes = {
            code for rule in case["rules"] if (code := SHAPE_RULE_CODES[rule]) is not None
        }
        assert expected == mapped_codes
    if "public_symbols" in case:
        parsed = lint_python._parse_files([path], path.parent)[0][0]
        explicit, _ = lint_python._explicit_all(parsed.tree)
        assert explicit is not None
        assert len(explicit) == case["public_symbols"]


@pytest.mark.unit
def test_size_and_class_count_are_not_architecture_rules(tmp_path: Path) -> None:
    module = tmp_path / "cohesive.py"
    classes = "\n\n".join(f"class Value{index}:\n    pass" for index in range(12))
    padding = "\n".join("# cohesive value documentation" for _ in range(320))
    module.write_text(
        f'"""One cohesive value family."""\n\n{classes}\n{padding}\n', encoding="utf-8"
    )

    assert _codes(tmp_path) == set()


@pytest.mark.unit
def test_locator_allowance_subjects_match_the_frozen_phase_1_inventory() -> None:
    manifest = json.loads(
        (
            REPOSITORY_ROOT
            / "tests"
            / "fixtures"
            / "post_collaboration_compatibility_surface.json"
        ).read_text(encoding="utf-8")
    )
    paths = {
        *manifest["locator_census"]["current_modules"],
        *(item["path"] for item in manifest["dynamic_module_lookups"]),
        *(item["path"] for item in manifest["local_import_locators"]),
    }
    findings = lint_python.scan_runtime_locators(
        [REPOSITORY_ROOT / path for path in sorted(paths)], REPOSITORY_ROOT
    )

    rpc_actual = Counter(
        finding.path for finding in findings if "_rpc_mod" in finding.message
    )
    rpc_expected = {
        path: sum(
            counts[key]
            for key in ("definitions", "loaded_references", "import_bindings", "exported_names")
        )
        for path, counts in manifest["locator_census"]["current_modules"].items()
    }
    assert dict(rpc_actual) == rpc_expected

    dynamic_actual = {
        (finding.path, finding.line, finding.column - 1)
        for finding in findings
        if "sys.modules" in finding.message or "importlib.import_module" in finding.message
    }
    dynamic_expected = {
        (item["path"], item["line"], item["column"])
        for item in manifest["dynamic_module_lookups"]
    }
    assert dynamic_actual == dynamic_expected

    local_actual = {
        (finding.path, finding.line, finding.column - 1)
        for finding in findings
        if finding.message.startswith("local import")
    }
    local_expected = {
        (item["path"], item["line"], item["column"])
        for item in manifest["local_import_locators"]
    }
    assert local_actual == local_expected


@pytest.mark.unit
def test_exact_allowance_suppresses_only_its_fingerprinted_finding(tmp_path: Path) -> None:
    module = tmp_path / "capabilities" / "grab_bag.py"
    module.parent.mkdir()
    module.write_text(
        "from capabilities.fem.mesh import mesh\n"
        "from capabilities.sketch.constraints import constrain\n",
        encoding="utf-8",
    )
    finding = _findings(tmp_path)[0]
    allowance = lint_python.Allowance(
        code=finding.code,
        path=finding.path,
        line=finding.line,
        column=finding.column,
        fingerprint=finding.fingerprint,
        reason="test legacy occurrence",
        removal_phase=3,
    )

    assert lint_python.apply_allowances([finding], [allowance], ["."]) == []

    changed = lint_python.Violation(
        finding.path,
        finding.line,
        finding.column,
        finding.code,
        finding.message,
        "0" * 20,
    )
    results = lint_python.apply_allowances([changed], [allowance], ["."])
    assert {result.code for result in results} == {finding.code, "ARCH099"}


@pytest.mark.unit
def test_allowance_manifest_rejects_globs_and_requires_removal_metadata(tmp_path: Path) -> None:
    allowance_file = tmp_path / "allowances.json"
    allowance_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allowances": [
                    {
                        "code": "ARCH103",
                        "path": "addon/**/rpc_server.py",
                        "line": 1,
                        "column": 1,
                        "fingerprint": "0" * 20,
                        "reason": "legacy locator",
                        "removal_phase": 17,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="exact"):
        lint_python.load_allowances(allowance_file)


@pytest.mark.unit
def test_stale_allowance_is_a_policy_failure() -> None:
    allowance = lint_python.Allowance(
        code="ARCH105",
        path="addon/FreeCADMCP/old_shim.py",
        line=4,
        column=1,
        fingerprint="0" * 20,
        reason="legacy executable shim",
        removal_phase=6,
    )

    findings = lint_python.apply_allowances([], [allowance], ["addon/FreeCADMCP"])

    assert len(findings) == 1
    assert findings[0].code == "ARCH099"
    assert "stale architecture allowance" in findings[0].message


@pytest.mark.unit
def test_architecture_only_cli_skips_ruff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "pass"
    source_root.mkdir()
    (source_root / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    called = False

    def fail_if_called(files: list[Path], fix: bool) -> int:
        nonlocal called
        called = True
        return 1

    monkeypatch.chdir(REPOSITORY_ROOT)
    monkeypatch.setattr(lint_python, "run_ruff", fail_if_called)

    assert lint_python.main(["--architecture-only", str(source_root)]) == 0
    assert called is False
