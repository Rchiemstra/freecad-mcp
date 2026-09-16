"""Native qualification matrix for typed ``bounding_box``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"])
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box")


def test_bounding_box_native_success_observes():
    check_query_success("bounding_box", _KIND, _RUN_ARGS)


def test_bounding_box_native_missing_document_keeps_typed_error():
    check_query_missing("bounding_box", _RUN_ARGS_MISSING)
