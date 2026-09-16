"""Contracts for the non-authoritative historic sidecar decoder."""

from __future__ import annotations

import ast as _ast
import contextlib as _contextlib
import importlib as _importlib
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
from addon.FreeCADMCP.document_lease import model as _model_mod
from addon.FreeCADMCP.document_lease import sidecar as _sidecar_mod
from addon.FreeCADMCP.document_lease.types import transitions as _transitions_mod
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
    parse_sidecar_bytes as _parse_sidecar_bytes,
)
from addon.FreeCADMCP.document_lease.sidecar_ops import codec as _codec_mod
from addon.FreeCADMCP.document_lease.sidecar_ops.constants import (
    MAX_SIDECAR_BYTES as _MAX_SIDECAR_BYTES,
)
from addon.FreeCADMCP.document_lease.sidecar_types.sidecar_malformed_error import (
    SidecarMalformedError as _SidecarMalformedError,
)
from addon.FreeCADMCP.document_lease.sidecar_types.sidecar_too_large_error import (
    SidecarTooLargeError as _SidecarTooLargeError,
)

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


@_contextlib.contextmanager
def _isolated_installed_import(module_name: str):
    """Import one installed spelling without borrowing cached alias modules."""

    installed_addon_root = str(_Path(_sidecar_mod.__file__).parents[1])
    evicted = {
        name: module
        for name, module in list(_sys.modules.items())
        if name == "document_lease" or name.startswith("document_lease.")
    }
    for name in evicted:
        _sys.modules.pop(name, None)
    _sys.path.insert(0, installed_addon_root)
    try:
        yield _importlib.import_module(module_name)
    finally:
        _sys.path.remove(installed_addon_root)
        for name in list(_sys.modules):
            if name == "document_lease" or name.startswith("document_lease."):
                _sys.modules.pop(name, None)
        _sys.modules.update(evicted)


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
    ids=("malformed-json", "invalid-utf8", "oversized-payload"),
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
def test_historic_sidecar_public_projection_redacts_nested_secrets(
    tmp_path: _Path,
) -> None:
    record, _encoded = _encoded_record(tmp_path)
    payload = record.to_sidecar_dict(include_task_summary=True)
    secrets = (
        "raw-operation-secret",
        "raw-task-secret",
        "raw-owner-secret",
        "raw-error-secret",
    )
    payload["token_fingerprint"] = "sha256:" + "b" * 64
    payload["lease"]["current_operation"] = f"token={secrets[0]}"
    payload["lease"]["task_summary"] = f"diagnostic={secrets[1]}"
    payload["owner"]["client"] = f"Bearer {secrets[2]}"
    payload["document_state"]["error"] = {
        "code": f"credential={secrets[3]}",
        "message": f"authorization={secrets[3]}",
        "at": "2026-07-22T00:00:02Z",
        "request_id": f"token={secrets[3]}",
    }

    decoded = _decode_historic_sidecar_bytes(
        _json.dumps(payload).encode("utf-8")
    )
    public_text = _json.dumps(decoded.to_public_dict(), sort_keys=True)

    assert "token_fingerprint" not in public_text
    assert "current_operation" not in public_text
    assert "task_summary" not in public_text
    assert "error" not in decoded.to_public_dict()["document_state"]
    assert all(secret not in public_text for secret in secrets)


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
def test_historic_decoder_is_exported_with_decoder_only_sidecar_contract(
    tmp_path: _Path,
) -> None:
    record, encoded = _encoded_record(tmp_path)

    assert _sidecar_mod.decode_historic_sidecar_bytes is _decode_historic_sidecar_bytes
    assert "decode_historic_sidecar_bytes" in _sidecar_mod.__all__
    with _isolated_installed_import("document_lease.sidecar") as installed_sidecar:
        assert _Path(installed_sidecar.__file__).resolve() == _Path(
            _sidecar_mod.__file__
        ).resolve()
        installed_record = installed_sidecar.decode_historic_sidecar_bytes(encoded)
    assert callable(installed_sidecar.decode_historic_sidecar_bytes)
    assert installed_record.to_public_dict() == _decode_historic_sidecar_bytes(
        encoded
    ).to_public_dict()
    assert _parse_sidecar_bytes is _codec_mod.parse_sidecar_bytes
    assert _parse_sidecar_bytes(encoded) == record
    assert "guard_path_for" in _sidecar_mod.__all__
    assert "sidecar_path_for" in _sidecar_mod.__all__
    for retired_name in (
        "SidecarStore",
        "create_sidecar",
        "replace_sidecar",
        "delete_sidecar",
    ):
        assert not hasattr(_sidecar_mod, retired_name)


@_pytest.mark.unit
@_pytest.mark.parametrize(
    "module_name, canonical_module, required_names, retired_names",
    [
        (
            "document_lease.model",
            _model_mod,
            ("HistoricLeaseRecord", "LeaseRecord", "decode_historic_lease_record"),
            ("validate_transition",),
        ),
        (
            "document_lease.types.transitions",
            _transitions_mod,
            ("ALLOWED_TRANSITIONS", "TERMINAL_STATES"),
            ("validate_transition",),
        ),
        (
            "document_lease.sidecar",
            _sidecar_mod,
            tuple(_sidecar_mod.__all__),
            ("SidecarStore", "create_sidecar", "delete_sidecar", "replace_sidecar"),
        ),
    ],
)
def test_installed_alias_modules_are_isolated_and_resolve_to_source(
    module_name: str,
    canonical_module,
    required_names: tuple[str, ...],
    retired_names: tuple[str, ...],
) -> None:
    prior_alias_modules = {
        name: module
        for name, module in _sys.modules.items()
        if name == "document_lease" or name.startswith("document_lease.")
    }
    with _isolated_installed_import(module_name) as installed_module:
        assert _Path(installed_module.__file__).resolve() == _Path(
            canonical_module.__file__
        ).resolve()
        assert all(hasattr(installed_module, name) for name in required_names)
        assert not any(hasattr(installed_module, name) for name in retired_names)
    restored_alias_modules = {
        name: module
        for name, module in _sys.modules.items()
        if name == "document_lease" or name.startswith("document_lease.")
    }
    assert restored_alias_modules == prior_alias_modules
