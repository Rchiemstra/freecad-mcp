"""Native qualification matrix for typed ``create_assembly_joint``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "assembly_with_two_parts"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx.get("assembly", "Assembly"), "Fixed", ctx.get("a", "A"), ctx.get("b", "B"))
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Assembly", "Fixed", "A", "B")


def test_create_assembly_joint_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_assembly_joint", _KIND, _RUN_ARGS, monkeypatch)


def test_create_assembly_joint_native_validation_failure_restores():
    check_validation_failure("create_assembly_joint", _KIND, _RUN_ARGS)


def test_create_assembly_joint_native_missing_document_keeps_typed_error():
    check_missing_document("create_assembly_joint", _RUN_ARGS_MISSING)
