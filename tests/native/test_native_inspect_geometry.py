"""Native qualification matrix for typed ``inspect_geometry``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], None)
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box", None)


def test_inspect_geometry_native_success_observes():
    check_query_success("inspect_geometry", _KIND, _RUN_ARGS)


def test_inspect_geometry_native_missing_document_keeps_typed_error():
    check_query_missing("inspect_geometry", _RUN_ARGS_MISSING)
