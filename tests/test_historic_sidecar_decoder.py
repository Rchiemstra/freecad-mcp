"""Contracts for the non-authoritative historic sidecar decoder."""

from __future__ import annotations

import ast as _ast
import inspect as _inspect
import json as _json
import os as _os
import sys as _sys
import traceback as _traceback
import uuid as _uuid_module
from dataclasses import FrozenInstanceError as _FrozenInstanceError
from pathlib import Path as _Path

import pytest as _pytest

from addon.FreeCADMCP.document_lease import historic_sidecar as historic_sidecar_mod
from addon.FreeCADMCP.document_lease import sidecar as _sidecar_mod
from addon.FreeCADMCP.document_lease.historic_sidecar import (
    decode_historic_sidecar_bytes as _decode_historic_sidecar_bytes,
)
from addon.FreeCADMCP.document_lease.model import (
    DocumentIdentity as _DocumentIdentity,
)
from addon.FreeCADMCP.document_lease.model import (
    FileBaseline as _FileBaseline,
)
from addon.FreeCADMCP.document_lease.model import (
    HistoricLeaseRecord as _HistoricLeaseRecord,
)
from addon.FreeCADMCP.document_lease.model import (
    LeaseOwner as _LeaseOwner,
)
from addon.FreeCADMCP.document_lease.model import (
    LeaseRecord as _LeaseRecord,
)
from addon.FreeCADMCP.document_lease.model import (
    LeaseState as _LeaseState,
)
from addon.FreeCADMCP.document_lease.model import (
    decode_historic_lease_record as _decode_historic_lease_record,
)
from addon.FreeCADMCP.document_lease.model import (
    token_fingerprint as _token_fingerprint,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    MAX_SIDECAR_BYTES as _MAX_SIDECAR_BYTES,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    SidecarMalformedError as _SidecarMalformedError,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    SidecarStore as _SidecarStore,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    SidecarTooLargeError as _SidecarTooLargeError,
)
from addon.FreeCADMCP.document_lease.sidecar import (
    parse_sidecar_bytes as _parse_sidecar_bytes,
)
from addon.FreeCADMCP.document_lease.sidecar_ops import codec as _codec_mod

__all__: list[str] = []


def _uuid() -> str:
    return str(_uuid_module.uuid4())


def _record(document_path: _Path) -> _LeaseRecord:
    return _LeaseRecord(
        lease_id=_uuid(),
        generation=1,
        token_fingerprint=_token_fingerprint("historic-secret"),
        document=_DocumentIdentity(
            session_uuid=_uuid(),
            name="Historic Model",
            canonical_path=str(document_path),
            comparison_key=_os.path.normcase(str(document_path)),
        ),
        owner=_LeaseOwner(
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
        state=_LeaseState.LOCKED_IDLE,
        baseline=_FileBaseline(
            mtime_ns=1, size=4, sha256="0" * 64, file_identity=None
        ),
        validation_complete=True,
    )


def _encoded_record(tmp_path: _Path) -> tuple[_LeaseRecord, bytes]:
    record = _record(tmp_path / "historic.FCStd")
    return record, _json.dumps(record.to_sidecar_dict()).encode("utf-8")


@_pytest.mark.unit
def test_historic_sidecar_round_trip_returns_immutable_projection(tmp_path: _Path) -> None:
    record, encoded = _encoded_record(tmp_path)

    decoded = _decode_historic_sidecar_bytes(encoded)

    assert isinstance(decoded, _HistoricLeaseRecord)
    assert decoded == _decode_historic_lease_record(record.to_sidecar_dict())
    assert not hasattr(decoded, "__dict__")
    assert not hasattr(decoded, "lease_id")
    assert not any(
        hasattr(decoded, name)
        for name in ("revised", "transitioned", "create", "replace", "delete")
    )
    with _pytest.raises(_FrozenInstanceError):
        decoded._payload = {}  # type: ignore[misc]


@_pytest.mark.unit
@_pytest.mark.parametrize(
    "data, error",
    [
        (b"{", _SidecarMalformedError),
        (b"\xff", _SidecarMalformedError),
        (b"{" + b"x" * _MAX_SIDECAR_BYTES, _SidecarTooLargeError),
    ],
)
def test_historic_sidecar_rejects_bad_bytes(
    data: bytes, error: type[Exception]
) -> None:
    with _pytest.raises(error):
        _decode_historic_sidecar_bytes(data)


@_pytest.mark.unit
def test_historic_sidecar_errors_are_publicly_redacted(tmp_path: _Path) -> None:
    record, _encoded = _encoded_record(tmp_path)
    payload = record.to_sidecar_dict()
    secret = "raw-secret-must-not-leak"
    payload["token_fingerprint"] = secret

    with _pytest.raises(_SidecarMalformedError) as error:
        _decode_historic_sidecar_bytes(_json.dumps(payload).encode("utf-8"))

    formatted = "".join(
        _traceback.format_exception(
            type(error.value), error.value, error.value.__traceback__
        )
    )
    assert secret not in str(error.value)
    assert secret not in formatted
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@_pytest.mark.unit
def test_historic_sidecar_normalizes_deep_json_without_retaining_it() -> None:
    deeply_nested = b"[" * 2_000 + b"0" + b"]" * 2_000

    with _pytest.raises(_SidecarMalformedError) as error:
        _decode_historic_sidecar_bytes(deeply_nested)

    assert error.value.__cause__ is None
    assert error.value.__context__ is None


@_pytest.mark.unit
def test_historic_decoder_has_no_live_authority_dependencies_or_writes(
    tmp_path: _Path,
) -> None:
    record, encoded = _encoded_record(tmp_path)
    source = _inspect.getsource(historic_sidecar_mod)
    tree = _ast.parse(source)
    forbidden_names = {
        "SidecarStore",
        "create",
        "replace",
        "delete",
        "validate_transition",
        "revised",
        "transitioned",
    }
    assert not {
        node.id for node in _ast.walk(tree) if isinstance(node, _ast.Name)
    } & forbidden_names

    before = set(tmp_path.iterdir())
    assert _decode_historic_sidecar_bytes(encoded) == _decode_historic_lease_record(
        record.to_sidecar_dict()
    )
    assert set(tmp_path.iterdir()) == before


@_pytest.mark.unit
def test_historic_decoder_is_exported_without_changing_live_sidecar_contract(
    tmp_path: _Path,
) -> None:
    record, encoded = _encoded_record(tmp_path)

    assert _sidecar_mod.decode_historic_sidecar_bytes is _decode_historic_sidecar_bytes
    assert "decode_historic_sidecar_bytes" in _sidecar_mod.__all__
    installed_addon_root = str(_Path(_sidecar_mod.__file__).parents[1])
    _sys.path.insert(0, installed_addon_root)
    try:
        import document_lease.sidecar as installed_sidecar

        installed_record = installed_sidecar.decode_historic_sidecar_bytes(encoded)
    finally:
        _sys.path.remove(installed_addon_root)
    assert callable(installed_sidecar.decode_historic_sidecar_bytes)
    assert installed_record.to_public_dict() == _decode_historic_sidecar_bytes(
        encoded
    ).to_public_dict()
    assert _parse_sidecar_bytes is _codec_mod.parse_sidecar_bytes
    assert _parse_sidecar_bytes(encoded) == record

    path = tmp_path / "live.FCStd.freecad-mcp.lock"
    store = _SidecarStore()
    store.create(path, record)
    assert store.read(path) == record
    store.delete(path, expected=record)
    assert not path.exists()
