"""Native qualification matrix for typed ``get_dependency_graph``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"])
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box")


def test_get_dependency_graph_native_success_observes():
    check_query_success("get_dependency_graph", _KIND, _RUN_ARGS)


def test_get_dependency_graph_native_missing_document_keeps_typed_error():
    check_query_missing("get_dependency_graph", _RUN_ARGS_MISSING)
