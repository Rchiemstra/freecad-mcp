"""Native qualification matrix for typed ``match_subshape``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], "Face1", ctx["box"], 10, 1.0)
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box", "Face1", "Box", 10, 1.0)


def test_match_subshape_native_success_observes():
    check_query_success("match_subshape", _KIND, _RUN_ARGS)


def test_match_subshape_native_missing_document_keeps_typed_error():
    check_query_missing("match_subshape", _RUN_ARGS_MISSING)
