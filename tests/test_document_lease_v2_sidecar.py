"""Decoder-only contracts for retired schema-v2 lease sidecars."""

from __future__ import annotations

import ast
import inspect
import json
import os
import uuid
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from addon.FreeCADMCP.document_lease import sidecar as sidecar_mod
from addon.FreeCADMCP.document_lease.model import (
    MAX_PERSISTED_TASK_SUMMARY_CHARS,
    DocumentIdentity,
    FileBaseline,
    LeaseOwner,
    LeaseRecord,
    LeaseState,
    SaveAsMigration,
    SaveAsMigrationRole,
    sanitize_persisted_task_summary,
    token_fingerprint,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    decode_historic_sidecar_bytes,
    parse_sidecar_bytes,
    validate_sidecar_payload,
)
from addon.FreeCADMCP.document_lease.sidecar_ops.constants import MAX_SIDECAR_BYTES
from addon.FreeCADMCP.document_lease.sidecar_types.sidecar_malformed_error import (
    SidecarMalformedError,
)
from addon.FreeCADMCP.document_lease.sidecar_types.sidecar_too_large_error import (
    SidecarTooLargeError,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _record(document_path: Path, *, token: str = "top-secret-token") -> LeaseRecord:
    return LeaseRecord(
        lease_id=_uuid(),
        generation=1,
        token_fingerprint=token_fingerprint(token),
        document=DocumentIdentity(
            session_uuid=_uuid(),
            name="Model",
            canonical_path=str(document_path),
            comparison_key=os.path.normcase(str(document_path)),
        ),
        owner=LeaseOwner(
            addon_profile_id=_uuid(),
            addon_runtime_id=_uuid(),
            freecad_pid=100,
            freecad_process_started_at="2026-07-22T00:00:00Z",
            boot_id="boot",
            mcp_instance_id=_uuid(),
            mcp_pid=200,
            mcp_process_started_at="2026-07-22T00:00:01Z",
            hostname="host",
            mcp_hostname="host",
            client="pytest",
            agent_id="agent",
        ),
        state=LeaseState.LOCKED_IDLE,
        baseline=FileBaseline(
            mtime_ns=1, size=4, sha256="0" * 64, file_identity=None
        ),
        validation_complete=True,
    )


def _migration_record(source: Path, destination: Path) -> LeaseRecord:
    return replace(
        _record(source),
        migration=SaveAsMigration(
            migration_id=_uuid(),
            source_canonical_path=str(source),
            source_comparison_key=os.path.normcase(str(source)),
            destination_canonical_path=str(destination),
            destination_comparison_key=os.path.normcase(str(destination)),
            role=SaveAsMigrationRole.SOURCE,
        ),
    )


@pytest.mark.unit
def test_sidecar_facade_retains_only_non_authoritative_compatibility_names(
    tmp_path: Path,
) -> None:
    assert sidecar_mod.__all__ == [
        "GUARD_SUFFIX",
        "MAX_SIDECAR_BYTES",
        "SIDECAR_SUFFIX",
        "SidecarAtomicityError",
        "SidecarCommitUncertainError",
        "SidecarConflictError",
        "SidecarError",
        "SidecarExistsError",
        "SidecarLockError",
        "SidecarMalformedError",
        "SidecarNetworkPathError",
        "SidecarNotFoundError",
        "SidecarPermissionError",
        "SidecarTooLargeError",
        "decode_historic_sidecar_bytes",
        "guard_path_for",
        "parse_sidecar_bytes",
        "sidecar_path_for",
        "validate_sidecar_payload",
    ]
    assert all(hasattr(sidecar_mod, name) for name in sidecar_mod.__all__)
    assert sidecar_mod.decode_historic_sidecar_bytes is decode_historic_sidecar_bytes
    assert sidecar_mod.parse_sidecar_bytes is parse_sidecar_bytes
    assert sidecar_mod.validate_sidecar_payload is validate_sidecar_payload

    forbidden = {
        "SidecarStore",
        "create_sidecar",
        "replace_sidecar",
        "delete_sidecar",
        "open_guard",
        "process_lock",
        "harden_permissions",
        "matches_cas",
    }
    assert not forbidden & set(vars(sidecar_mod))
    tree = ast.parse(inspect.getsource(sidecar_mod))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    forbidden_imports = {
        "sidecar_ops.cas",
        "sidecar_ops.fsync_directory",
        "sidecar_ops.guard",
        "sidecar_ops.io",
        "sidecar_ops.network_path",
        "sidecar_ops.permissions",
        "sidecar_ops.store_create",
        "sidecar_ops.store_delete",
        "sidecar_ops.store_replace",
    }
    assert not imported_modules & forbidden_imports

    before = set(tmp_path.iterdir())
    document_path = tmp_path / "model.FCStd"
    sidecar_path = sidecar_mod.sidecar_path_for(document_path)
    guard_path = sidecar_mod.guard_path_for(sidecar_path)
    assert sidecar_path == Path(f"{document_path}{sidecar_mod.SIDECAR_SUFFIX}")
    assert guard_path == Path(f"{sidecar_path}{sidecar_mod.GUARD_SUFFIX}")
    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
def test_parse_sidecar_bytes_returns_frozen_read_only_compatibility_record(
    tmp_path: Path,
) -> None:
    token = "raw-token-must-not-leak"
    record = _record(tmp_path / "model.FCStd", token=token)
    encoded = json.dumps(record.to_sidecar_dict()).encode()

    parsed = parse_sidecar_bytes(encoded)

    assert parsed == record
    assert token.encode() not in encoded
    assert "token_fingerprint" not in parsed.to_public_dict()
    assert token not in json.dumps(parsed.to_public_dict())
    assert not hasattr(parsed, "revised")
    assert not hasattr(parsed, "transitioned")
    with pytest.raises(FrozenInstanceError):
        parsed.state = LeaseState.STALE  # type: ignore[misc]


@pytest.mark.unit
def test_parsed_public_projection_drops_diagnostics_and_arbitrary_secrets(
    tmp_path: Path,
) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    secrets = (
        "opaque-operation-A9Q",
        "opaque-task-B8R",
        "opaque-error-C7S",
        "opaque-owner-D6T",
    )
    payload["lease"]["current_operation"] = f"token={secrets[0]}"
    payload["lease"]["task_summary"] = f"diagnostic={secrets[1]}"
    payload["document_state"]["error"] = {
        "code": f"credential={secrets[2]}",
        "message": f"authorization={secrets[2]}",
        "at": "2026-07-22T00:00:02Z",
        "request_id": f"token={secrets[2]}",
    }
    payload["owner"]["client"] = f"Bearer {secrets[3]}"

    parsed = parse_sidecar_bytes(json.dumps(payload).encode())
    public = parsed.to_public_dict()
    public_text = json.dumps(public, sort_keys=True)

    assert "token_fingerprint" not in public_text
    assert "current_operation" not in public["lease"]
    assert "task_summary" not in public["lease"]
    assert "error" not in public["document_state"]
    assert public["owner"]["client"] == "<redacted>"
    assert all(secret not in public_text for secret in secrets)


@pytest.mark.unit
def test_mapping_decoder_does_not_retain_mutable_payload_backing(
    tmp_path: Path,
) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    validated = validate_sidecar_payload(payload)

    parsed = LeaseRecord.from_sidecar_dict(validated)
    payload["lease"]["state"] = LeaseState.STALE.value
    payload["owner"]["client"] = "changed after decode"
    payload["document"]["name"] = "changed after decode"

    assert parsed.state == LeaseState.LOCKED_IDLE
    assert parsed.owner.client == "pytest"
    assert parsed.document.name == "Model"


@pytest.mark.unit
def test_decoders_do_not_write_to_the_filesystem(tmp_path: Path) -> None:
    record = _record(tmp_path / "model.FCStd")
    encoded = json.dumps(record.to_sidecar_dict()).encode()
    before = set(tmp_path.iterdir())

    assert parse_sidecar_bytes(encoded) == record
    assert decode_historic_sidecar_bytes(encoded).to_sidecar_dict() == (
        record.to_sidecar_dict()
    )
    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
def test_save_as_migration_round_trip_remains_decoder_compatible(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.FCStd"
    destination = tmp_path / "destination.FCStd"
    record = _migration_record(source, destination)
    before = set(tmp_path.iterdir())

    parsed = parse_sidecar_bytes(json.dumps(record.to_sidecar_dict()).encode())

    assert parsed == record
    assert parsed.to_public_dict()["migration"]["role"] == "source"
    assert "token_fingerprint" not in json.dumps(parsed.to_public_dict())
    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        lambda migration: migration.update(migration_id="not-a-uuid"),
        lambda migration: migration.update(role="peer"),
        lambda migration: migration.update(role="destination"),
        lambda migration: migration.update(unexpected=True),
        lambda migration: migration["source"].update(comparison_key=None),
        lambda migration: migration["destination"].update(
            canonical_path=migration["source"]["canonical_path"],
            comparison_key=migration["source"]["comparison_key"],
        ),
    ],
)
def test_parser_rejects_malformed_migration_linkage_without_writes(
    tmp_path: Path,
    mutation,
) -> None:
    payload = _migration_record(
        tmp_path / "source.FCStd", tmp_path / "destination.FCStd"
    ).to_sidecar_dict()
    mutation(payload["migration"])
    before = set(tmp_path.iterdir())

    with pytest.raises(SidecarMalformedError):
        parse_sidecar_bytes(json.dumps(payload).encode())

    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
def test_parser_preserves_bounded_task_summary_without_writes(tmp_path: Path) -> None:
    summary = "historic task metadata"
    record = replace(_record(tmp_path / "model.FCStd"), task_summary=summary)
    assert record.to_sidecar_dict()["lease"]["task_summary"] == ""
    payload = record.to_sidecar_dict(include_task_summary=True)
    before = set(tmp_path.iterdir())

    parsed = parse_sidecar_bytes(json.dumps(payload).encode())

    assert parsed.task_summary == summary
    assert "task_summary" not in parsed.to_public_dict()["lease"]
    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
def test_task_summary_opt_in_normalizes_controls_and_caps_length(
    tmp_path: Path,
) -> None:
    summary = "  Build\tPad\x00for\u200b customer  " + "x" * 400
    record = replace(_record(tmp_path / "model.FCStd"), task_summary=summary)
    expected = sanitize_persisted_task_summary(summary)
    before = set(tmp_path.iterdir())

    persisted = record.to_sidecar_dict(include_task_summary=True)["lease"][
        "task_summary"
    ]

    assert persisted == expected
    assert persisted.startswith("Build Pad for customer ")
    assert len(persisted) <= MAX_PERSISTED_TASK_SUMMARY_CHARS
    assert all(character.isprintable() for character in persisted)
    assert record.task_summary == summary
    assert set(tmp_path.iterdir()) == before

    boundary = "x" * (MAX_PERSISTED_TASK_SUMMARY_CHARS - 1) + "  y"
    assert len(sanitize_persisted_task_summary(boundary)) <= (
        MAX_PERSISTED_TASK_SUMMARY_CHARS
    )


@pytest.mark.unit
def test_parser_rejects_oversized_task_summary_without_writes(
    tmp_path: Path,
) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    payload["lease"]["task_summary"] = "x" * 1_025
    before = set(tmp_path.iterdir())

    with pytest.raises(SidecarMalformedError):
        parse_sidecar_bytes(json.dumps(payload).encode())

    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(record_revision=1)
        or data["lease"].update(state_revision=2),
        lambda data: data["document_state"].update(
            last_mutation_revision=1, last_verified_save_revision=2
        ),
        lambda data: data["lease"].update(state="USER_INTERVENED"),
        lambda data: data["lease"].update(state="LOCKED_ERROR"),
    ],
)
def test_parser_enforces_cross_field_rules_without_writes(
    tmp_path: Path,
    mutation,
) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    mutation(payload)
    before = set(tmp_path.iterdir())

    with pytest.raises(SidecarMalformedError):
        parse_sidecar_bytes(json.dumps(payload).encode())

    assert set(tmp_path.iterdir()) == before


@pytest.mark.unit
def test_parser_keeps_older_schema_v2_shapes_compatible(tmp_path: Path) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    payload.pop("migration")
    payload["owner"].pop("mcp_hostname")

    parsed = parse_sidecar_bytes(json.dumps(payload).encode())

    assert parsed.migration is None
    assert parsed.owner.mcp_hostname == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(schema_version=99),
        lambda data: data.update(token_fingerprint="raw-token"),
        lambda data: data["lease"].update(state="MADE_UP"),
        lambda data: data.update(unexpected=True),
        lambda data: data["document_state"].update(dirty="yes"),
    ],
)
def test_parser_strictly_rejects_invalid_fields(
    tmp_path: Path, mutation
) -> None:
    payload = _record(tmp_path / "model.FCStd").to_sidecar_dict()
    mutation(payload)

    with pytest.raises(SidecarMalformedError):
        parse_sidecar_bytes(json.dumps(payload).encode())


@pytest.mark.unit
@pytest.mark.parametrize("data", [b"{", b"\xff"])
def test_parser_rejects_malformed_bytes(data: bytes) -> None:
    with pytest.raises(SidecarMalformedError):
        parse_sidecar_bytes(data)


@pytest.mark.unit
def test_parser_rejects_oversized_json_before_decoding() -> None:
    with pytest.raises(SidecarTooLargeError):
        parse_sidecar_bytes(b"{" + b"x" * MAX_SIDECAR_BYTES)
