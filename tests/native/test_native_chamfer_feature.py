"""Native qualification matrix for typed ``chamfer_feature``."""

from __future__ import annotations

import pytest

from tests.typed_feature_native_matrix import (
    check_apply_failure,
    check_duplicate_and_missing,
    check_inspection_failure,
    check_isolated_recovery,
    check_postcondition_cannot_write,
    check_recompute_failure,
    check_rich_model_restore,
    check_rollback_failure_fences,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KWARGS = {'doc_name': 'Doc', 'base_feature': 'Pad', 'chamfer_name': 'Chamfer', 'size': 1.0, 'edge_refs': None, 'body_name': None}
_KIND = 'edge_feature'
_CREATED = 'chamfer_name'


def test_chamfer_feature_native_success_inspects_after_recompute(monkeypatch):
    check_success("chamfer_feature", _KIND, _KWARGS, monkeypatch)


def test_chamfer_feature_native_validation_failure_restores_complete_state():
    check_validation_failure("chamfer_feature", _KIND, _KWARGS)


def test_chamfer_feature_native_apply_failure_restores_all_attempted_effects(monkeypatch):
    check_apply_failure("chamfer_feature", _KIND, _KWARGS, monkeypatch)


def test_chamfer_feature_native_recompute_failure_rolls_back(monkeypatch):
    check_recompute_failure("chamfer_feature", _KIND, _KWARGS, monkeypatch)


def test_chamfer_feature_native_rollback_failure_is_uncertain_and_fences_document(monkeypatch):
    check_rollback_failure_fences("chamfer_feature", _KIND, _KWARGS, monkeypatch)


def test_chamfer_feature_native_inspection_failure_rolls_back_after_recompute(monkeypatch):
    check_inspection_failure("chamfer_feature", _KIND, _KWARGS, monkeypatch)


def test_chamfer_feature_native_failure_isolated_and_healthy_rollback_recovers():
    check_isolated_recovery("chamfer_feature", _KIND, _KWARGS, _CREATED)


def test_chamfer_feature_native_duplicate_and_missing_document_keep_typed_errors():
    check_duplicate_and_missing("chamfer_feature", _KIND, _KWARGS)


@pytest.mark.parametrize("stage", ["apply", "recompute", "inspection", "validation"])
def test_chamfer_feature_native_rollback_restores_rich_model(monkeypatch, stage):
    check_rich_model_restore("chamfer_feature", _KIND, _KWARGS, monkeypatch, stage)


@pytest.mark.parametrize("write", ["property", "structure"])
def test_chamfer_feature_native_postcondition_cannot_write(write):
    check_postcondition_cannot_write("chamfer_feature", _KIND, _KWARGS, write)
