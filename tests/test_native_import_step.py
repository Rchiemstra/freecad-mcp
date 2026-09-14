"""Native qualification matrix for typed ``import_step``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_setup import export_temp_path, write_box_step
from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["path"])
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", export_temp_path(".step"))


def test_import_step_native_success_inspects_after_recompute(monkeypatch):
    check_success("import_step", _KIND, _RUN_ARGS, monkeypatch)


def test_import_step_native_validation_failure_restores():
    check_validation_failure("import_step", _KIND, _RUN_ARGS)


def test_import_step_native_missing_document_keeps_typed_error():
    check_missing_document("import_step", _RUN_ARGS_MISSING)
