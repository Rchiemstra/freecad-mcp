"""Native qualification for typed ``export_brep``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_export_missing, check_export_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx, dest: (doc_name, ctx["box"], str(dest))
_RUN_ARGS_MISSING = lambda doc_name, _ctx, dest: (doc_name, "Box", str(dest))


def test_export_brep_native_success_publishes():
    check_export_success("export_brep", _KIND, _RUN_ARGS)


def test_export_brep_native_missing_document_keeps_typed_error():
    check_export_missing("export_brep", _RUN_ARGS_MISSING)
