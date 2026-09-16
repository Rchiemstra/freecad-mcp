"""Unit tests for Part 3 identity selector and revision encoding."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.document_lease.types.document_selector import DocumentSelector
from addon.FreeCADMCP.part3_collaboration.identity import selector_from_mapping
from addon.FreeCADMCP.part3_collaboration.revisions import (
    conflict_payload_from_commit_result,
    encode_semantic_revision_key,
)
from addon.FreeCADMCP.part3_collaboration.types.part3_identity_selector import (
    Part3IdentitySelector,
)

pytestmark = pytest.mark.unit


def test_part3_selector_is_distinct_from_lease_document_selector() -> None:
    part3 = Part3IdentitySelector(
        document_uid="uid-1",
        document_instance_id=7,
        lifecycle_epoch=3,
        document_name="Model",
    )
    lease = DocumentSelector(
        document_session_uuid="lease-session",
        document_name="Model",
        canonical_path="/tmp/model.FCStd",
    )
    assert type(part3) is not DocumentSelector
    assert "document_uid" in part3.__dataclass_fields__
    assert "document_instance_id" in part3.__dataclass_fields__
    assert "lifecycle_epoch" in part3.__dataclass_fields__
    assert "document_session_uuid" in lease.__dataclass_fields__


def test_selector_from_mapping_requires_identity_fields() -> None:
    assert selector_from_mapping({"document_name": "Model"}) is None
    parsed = selector_from_mapping(
        {
            "document_uid": "uid",
            "document_instance_id": 2,
            "lifecycle_epoch": 1,
            "document_name": "Model",
        }
    )
    assert parsed is not None
    assert parsed.document_uid == "uid"
    assert parsed.document_instance_id == 2
    assert parsed.lifecycle_epoch == 1


def test_encode_semantic_revision_key_uses_kind_subject_property() -> None:
    assert encode_semantic_revision_key(
        {
            "kind": "ObjectProperty",
            "subject": "Target",
            "property_name": "Count",
        }
    ) == "ObjectProperty:Target:Count"
    assert encode_semantic_revision_key(
        {"kind": "ObjectModel", "subject": "Target"}
    ) == "ObjectModel:Target"


def test_conflict_payload_maps_native_conflicts() -> None:
    payload = conflict_payload_from_commit_result(
        {
            "status": "Conflict",
            "message": "revision mismatch",
            "conflicts": [
                {
                    "kind": "ObjectModel",
                    "subject": "Target",
                    "expected": 2,
                    "current": 3,
                }
            ],
        },
        operation_id="op-1",
    )
    assert payload["error_code"] == "DOCUMENT_CONFLICT"
    assert payload["changed_semantic_keys"] == ["ObjectModel:Target"]
    assert payload["expected_revisions"] == {"ObjectModel:Target": 2}
    assert payload["current_revisions"] == {"ObjectModel:Target": 3}
    assert payload["operation_id"] == "op-1"
