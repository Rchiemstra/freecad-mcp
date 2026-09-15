"""Native qualification matrix for typed ``snapshot``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, _ctx: (doc_name,)
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name,)


def test_snapshot_native_success_observes():
    check_query_success("snapshot", _KIND, _RUN_ARGS)


def test_snapshot_native_missing_document_keeps_typed_error():
    check_query_missing("snapshot", _RUN_ARGS_MISSING)
