"""Native qualification matrix for typed ``import_brep``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_setup import export_temp_path, write_box_brep
from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "import_brep"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["path"], "Imported")
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", export_temp_path(".brep"), "Imported")


def test_import_brep_native_success_inspects_after_recompute(monkeypatch):
    check_success("import_brep", _KIND, _RUN_ARGS, monkeypatch)


def test_import_brep_native_validation_failure_restores():
    check_validation_failure("import_brep", _KIND, _RUN_ARGS)


def test_import_brep_native_missing_document_keeps_typed_error():
    check_missing_document("import_brep", _RUN_ARGS_MISSING)
