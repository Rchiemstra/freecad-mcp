"""Native qualification matrix for typed ``center_of_mass``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "box"
_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"])
_RUN_ARGS_MISSING = lambda doc_name, _ctx: (doc_name, "Box")


def test_center_of_mass_native_success_observes():
    check_query_success("center_of_mass", _KIND, _RUN_ARGS)


def test_center_of_mass_native_missing_document_keeps_typed_error():
    check_query_missing("center_of_mass", _RUN_ARGS_MISSING)
