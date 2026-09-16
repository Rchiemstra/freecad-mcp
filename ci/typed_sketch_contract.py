"""Deprecated sketch gate entrypoint; delegates to the shared policy dispatcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ci.scan_execution_policy_gates import scan_op_architecture
from ci.scan_typed_feature_contract import main_for_op as _main_for_op

__all__ = ["main_for_op", "scan_sketch_op_architecture"]


def scan_sketch_op_architecture(
    root: Path,
    op: str,
    *,
    source_overrides: Mapping[str, str] | None = None,
) -> list[str]:
    return scan_op_architecture(root, op, source_overrides=source_overrides)


def main_for_op(op: str, argv: Sequence[str] | None = None) -> int:
    return _main_for_op(op, argv, typecheck=True)
