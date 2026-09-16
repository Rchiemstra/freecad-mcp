"""Native qualification matrix for typed ``audit_hardcoded_dimensions``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], True)
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box", True)


def test_audit_hardcoded_dimensions_native_success_observes():
    check_query_success("audit_hardcoded_dimensions", _KIND, _RUN_ARGS)


def test_audit_hardcoded_dimensions_native_missing_document_keeps_typed_error():
    check_query_missing("audit_hardcoded_dimensions", _RUN_ARGS_MISSING)
