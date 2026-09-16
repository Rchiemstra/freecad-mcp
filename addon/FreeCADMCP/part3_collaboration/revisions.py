from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def encode_semantic_revision_key(observation: Mapping[str, Any]) -> str:
    kind = str(observation.get("kind") or "")
    subject = str(observation.get("subject") or "")
    if kind == "ObjectProperty":
        property_name = str(observation.get("property_name") or "")
        return f"{kind}:{subject}:{property_name}"
    return f"{kind}:{subject}"


def revision_keys_from_observations(
    observations: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    keys: list[dict[str, str]] = []
    for observation in observations:
        kind = str(observation.get("kind") or "")
        if not kind:
            continue
        item: dict[str, str] = {"kind": kind}
        subject = observation.get("subject")
        if subject is not None:
            item["subject"] = str(subject)
        property_name = observation.get("property_name")
        if property_name is not None:
            item["property_name"] = str(property_name)
        keys.append(item)
    return keys


def conflict_payload_from_commit_result(
    commit_result: Mapping[str, Any],
    *,
    operation_id: str | None = None,
) -> dict[str, Any]:
    changed_semantic_keys: list[str] = []
    expected_revisions: dict[str, int] = {}
    current_revisions: dict[str, int] = {}
    for conflict in commit_result.get("conflicts") or []:
        if not isinstance(conflict, Mapping):
            continue
        key_id = encode_semantic_revision_key(conflict)
        changed_semantic_keys.append(key_id)
        expected = conflict.get("expected")
        current = conflict.get("current")
        if isinstance(expected, int):
            expected_revisions[key_id] = expected
        if isinstance(current, int):
            current_revisions[key_id] = current
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": "DOCUMENT_CONFLICT",
        "error": str(commit_result.get("message") or "document revision conflict"),
        "changed_semantic_keys": changed_semantic_keys,
        "expected_revisions": expected_revisions,
        "current_revisions": current_revisions,
    }
    if operation_id:
        payload["operation_id"] = operation_id
    return payload
