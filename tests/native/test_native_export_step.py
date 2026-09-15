"""Native qualification for typed ``export_step``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_export_missing, check_export_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx, dest: (doc_name, str(dest), [ctx["box"]])
_RUN_ARGS_MISSING = lambda doc_name, _ctx, dest: (doc_name, str(dest), None)


def test_export_step_native_success_publishes():
    check_export_success("export_step", _KIND, _RUN_ARGS)


def test_export_step_native_missing_document_keeps_typed_error():
    check_export_missing("export_step", _RUN_ARGS_MISSING)
