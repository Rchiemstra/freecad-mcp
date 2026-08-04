"""Focused contracts for the read-only historic lease decoder."""

from __future__ import annotations

import ast
import inspect
import json
import uuid
from dataclasses import FrozenInstanceError

import pytest

from addon.FreeCADMCP.document_lease import model as model_mod
from addon.FreeCADMCP.document_lease.model import (
    DocumentIdentity,
    HistoricLeaseRecord,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    decode_historic_lease_record,
)
from addon.FreeCADMCP.document_lease.types.transitions import ALLOWED_TRANSITIONS


def _uuid() -> str:
    return str(uuid.uuid4())


def _historic_sidecar() -> dict[str, object]:
    record = LeaseRecord(
        lease_id=_uuid(),
        generation=1,
        token_fingerprint="sha256:" + "a" * 64,
        document=DocumentIdentity(session_uuid=_uuid(), name="historic-model"),
        owner=LeaseOwner(
            addon_profile_id=_uuid(),
            addon_runtime_id=_uuid(),
            freecad_pid=100,
            freecad_process_started_at="2026-08-04T00:00:00Z",
            boot_id="boot",
            mcp_instance_id=_uuid(),
            mcp_pid=200,
            mcp_process_started_at="2026-08-04T00:00:01Z",
            hostname="host",
        ),
        state=LeaseState.LOCKED_IDLE,
    )
    payload = record.to_sidecar_dict(include_task_summary=True)
    payload["lease"]["current_operation"] = "token=historic-secret"
    payload["lease"]["task_summary"] = "diagnostic historic-secret"
    payload["document_state"]["error"] = {
        "code": "credential=historic-secret",
        "message": "diagnostic historic-secret",
        "at": "2026-08-04T00:00:02Z",
        "request_id": "token=historic-secret",
    }
    return payload


@pytest.mark.unit
def test_decoder_round_trips_and_returns_independent_sidecar_copies() -> None:
    payload = _historic_sidecar()
    historic = decode_historic_lease_record(payload)

    first = historic.to_sidecar_dict()
    second = historic.to_sidecar_dict()

    assert first == payload
    assert second == payload
    assert first is not second
    first["lease"]["state"] = LeaseState.STALE.value
    assert historic.to_sidecar_dict()["lease"]["state"] == LeaseState.LOCKED_IDLE.value


@pytest.mark.unit
def test_decoder_is_frozen_slotted_and_deeply_immutable() -> None:
    historic = decode_historic_lease_record(_historic_sidecar())

    with pytest.raises(TypeError):
        HistoricLeaseRecord()
    assert not hasattr(historic, "__dict__")
    with pytest.raises(FrozenInstanceError):
        historic._payload = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        historic._payload["lease"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        historic._payload["lease"]["state"] = LeaseState.STALE  # type: ignore[index]


@pytest.mark.unit
def test_decoder_public_shape_has_no_live_transition_or_authority_api() -> None:
    public_methods = {
        name
        for name, member in inspect.getmembers(HistoricLeaseRecord, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {"to_public_dict", "to_sidecar_dict"}
    assert not hasattr(HistoricLeaseRecord, "transitioned")
    assert not hasattr(HistoricLeaseRecord, "revised")
    decoder_source = "\n".join(
        inspect.getsource(member)
        for member in (
            HistoricLeaseRecord,
            model_mod._freeze_historic_value,
            model_mod._historic_hash,
            model_mod._redact_historic_public_value,
            model_mod._thaw_historic_value,
            model_mod._validated_historic_payload,
            decode_historic_lease_record,
        )
    )
    decoder_tree = ast.parse(decoder_source)
    forbidden = {
        "SidecarStore",
        "create",
        "create_sidecar",
        "delete",
        "delete_sidecar",
        "replace",
        "replace_sidecar",
        "revised",
        "transitioned",
        "validate_transition",
    }
    assert not {
        node.id for node in ast.walk(decoder_tree) if isinstance(node, ast.Name)
    } & forbidden
    assert not {
        node.attr for node in ast.walk(decoder_tree) if isinstance(node, ast.Attribute)
    } & forbidden


@pytest.mark.unit
def test_decoder_repr_and_public_data_are_redacted() -> None:
    historic = decode_historic_lease_record(_historic_sidecar())
    public = historic.to_public_dict()
    public_text = json.dumps(public, sort_keys=True)

    assert "historic-secret" not in repr(historic)
    assert "historic-secret" not in public_text
    assert "token_fingerprint" not in public_text
    assert "current_operation" not in public["lease"]
    assert "task_summary" not in public["lease"]
    assert "error" not in public["document_state"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload, error",
    [
        (None, ValueError),
        ([], ValueError),
        ({"schema_version": 2}, ValueError),
        ({**_historic_sidecar(), "schema_version": 999}, ValueError),
        ({**_historic_sidecar(), "record_kind": "not-a-lease"}, ValueError),
        ({**_historic_sidecar(), "lease": []}, ValueError),
        ({**_historic_sidecar(), "owner": object()}, ValueError),
        (
            {
                **_historic_sidecar(),
                "lease": {**_historic_sidecar()["lease"], "state": "unknown"},
            },
            ValueError,
        ),
        ({**_historic_sidecar(), "unexpected": "field"}, ValueError),
    ],
)
def test_decoder_rejects_malformed_direct_inputs(payload, error) -> None:
    with pytest.raises(error):
        decode_historic_lease_record(payload)  # type: ignore[arg-type]


@pytest.mark.unit
def test_transition_tables_are_read_only_without_changing_live_behavior() -> None:
    with pytest.raises(TypeError):
        ALLOWED_TRANSITIONS[LeaseState.ACQUIRING] = frozenset()  # type: ignore[index]
    with pytest.raises(AttributeError):
        ALLOWED_TRANSITIONS[LeaseState.ACQUIRING].add(LeaseState.UNLOCKED_SAVED)  # type: ignore[attr-defined]

    record = LeaseRecord(
        lease_id=_uuid(),
        generation=1,
        token_fingerprint="sha256:" + "a" * 64,
        document=DocumentIdentity(session_uuid=_uuid(), name="live-model"),
        owner=LeaseOwner(
            addon_profile_id=_uuid(),
            addon_runtime_id=_uuid(),
            freecad_pid=100,
            freecad_process_started_at="2026-08-04T00:00:00Z",
            boot_id="boot",
            mcp_instance_id=_uuid(),
            mcp_pid=200,
            mcp_process_started_at="2026-08-04T00:00:01Z",
            hostname="host",
        ),
        state=LeaseState.LOCKED_IDLE,
    )

    revised = record.revised(current_operation="Pad")
    transitioned = record.transitioned(LeaseState.LOCKED_EDITING)

    assert revised.record_revision == record.record_revision + 1
    assert revised.current_operation == "Pad"
    assert transitioned.state == LeaseState.LOCKED_EDITING
    assert transitioned.state_revision == record.state_revision + 1
    assert transitioned.record_revision == record.record_revision + 1
