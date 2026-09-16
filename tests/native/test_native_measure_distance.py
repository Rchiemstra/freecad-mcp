"""Native qualification matrix for typed ``measure_distance``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], ctx["box"])
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box", "Box")


def test_measure_distance_native_success_observes():
    check_query_success("measure_distance", _KIND, _RUN_ARGS)


def test_measure_distance_native_missing_document_keeps_typed_error():
    check_query_missing("measure_distance", _RUN_ARGS_MISSING)
