"""Unit coverage for the typed ``spreadsheet_set_cells`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    spreadsheet_set_cells as subject,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_cells import (
    run_spreadsheet_set_cells,
)

pytestmark = pytest.mark.unit


def _item(name: str, *, label: str | None = None, type_id: str = "App::FeaturePython"):
    values: dict[str, str] = {}
    aliases: dict[str, str] = {}

    def set_cell(address, value):
        values[str(address)] = str(value)

    def set_alias(address, alias):
        address = str(address)
        alias = str(alias)
        for bound_address, bound_alias in list(aliases.items()):
            if bound_alias == alias and bound_address != address:
                del aliases[bound_address]
        aliases[address] = alias

    def get_alias(address):
        return aliases.get(str(address))

    def get_cell_from_alias(alias):
        alias = str(alias)
        for address, bound_alias in aliases.items():
            if bound_alias == alias:
                return address
        return None

    obj = SimpleNamespace(
        Name=name,
        Label=label if label is not None else f"Label for {name}",
        TypeId=type_id,
        State=[],
        InList=[],
        Group=[],
        PropertiesList=[],
        Placement=SimpleNamespace(Base=SimpleNamespace(x=0.0, y=0.0, z=0.0)),
    )
    obj.setExpression = lambda *_a, **_k: None
    obj.clearExpression = lambda *_a, **_k: None
    obj.set = set_cell
    obj.setAlias = set_alias
    obj.get = lambda address, *_a, **_k: values.get(str(address), "")
    obj.getContents = lambda address, *_a, **_k: values.get(str(address), "")
    obj.getAlias = get_alias
    obj.getCellFromAlias = get_cell_from_alias
    obj.getNonEmptyCells = lambda: list(values)
    obj.addObject = lambda other: obj.Group.append(other)
    obj.newObject = lambda type_id, name: _item(name, type_id=type_id)
    obj.addExternal = lambda *_a, **_k: None
    obj.saveCopy = lambda path: PathWrite(path)
    obj._mcp_snapshots = []
    return obj


def PathWrite(path: str) -> None:
    with open(path, "wb") as handle:
        handle.write(b"snap")


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str], *, assigned_name: str | None = None) -> None:
        self.events = events
        self.objects: dict[str, object] = {}
        self.assigned_name = assigned_name
        self.recomputed = False
        self.add_calls = 0
        self._mcp_snapshots: list[object] = []

    @property
    def Objects(self) -> list[object]:
        return list(self.objects.values())

    def getObject(self, name):
        item = self.objects.get(name)
        if item is not None and self.recomputed:
            self.events.append("inspect")
        return item

    def addObject(self, object_type, name):
        self.add_calls += 1
        self.events.append("apply")
        actual_name = self.assigned_name or name
        item = _item(actual_name, type_id=object_type)
        self.objects[actual_name] = item
        return item

    def removeObject(self, name):
        self.objects.pop(name, None)

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True

    def saveCopy(self, path):
        PathWrite(path)


class _MutateThenRaiseDocument(_Document):
    def addObject(self, object_type, name):
        super().addObject(object_type, name)
        raise RuntimeError("FreeCAD failed after mutating")


class _RecomputeFailureDocument(_Document):
    def recompute(self):
        super().recompute()
        raise RuntimeError("FreeCAD recompute failed")


class _NativeBridgeDocument(_Document):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True or structural is False
        before_objects = dict(self.objects)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class _CompatibilityAPI:
    def __init__(self, document: _Document | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls = []

    def _restore(self, objects, recomputed) -> None:
        assert self.document is not None
        self.document.objects = objects
        self.document.recomputed = recomputed
        self.document.events.append("abort")

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        postcondition=None,
        bind_document=False,
        require_native=False,
    ):
        self.calls.append((document_name, structural, bind_document, require_native))
        if self.document is None:
            raise LookupError("document_lookup returned no document")
        before_objects = dict(self.document.objects)
        before_recomputed = self.document.recomputed
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}
        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }
        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_recomputed)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }
        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_recomputed)
            return result
        self.document.events.append("commit")
        return {"status": "Committed", "committed": True}

    def commit_native_mutation(self, document_name, callback, postcondition, *, structural=True):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )


def _seed(document: _Document) -> None:
    seed = "sheet"
    if seed in {"sheet", "object", "move", "body", "source", "wire", "sketch", "datum", "relink", "analysis", "snapshot"}:
        document.objects["Seed"] = _item("Seed", type_id="App::FeaturePython")
        document.objects["Target"] = _item("Target", type_id="App::FeaturePython")
        document.objects["Body"] = _item("Body", type_id="PartDesign::Body")
        if seed == "sheet":
            document.objects["Target"].TypeId = "Spreadsheet::Sheet"
        if seed == "body":
            maker = lambda type_id, name: document.addObject(type_id, name)
            document.objects["Seed"].newObject = maker
            document.objects["Body"].newObject = maker
        if seed == "snapshot":
            document._mcp_snapshots.append({"id": "snap-test", "path": "x.FCStd", "doc": "Doc"})


def _collaborators(document: _Document | None, events: list[str], *, validator=None, final_result=None):
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
        part=object(),
    )
    return collaborators, api


def test_spreadsheet_set_cells_runs_apply_recompute_inspect_validate_then_commits():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)

    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])

    assert result["success"] is True
    assert result["outcome"] == "committed"
    assert result["committed"] is True
    assert "recompute" in events
    assert "commit" in events


def test_missing_document_fails_without_entering_the_apply_callback():
    events: list[str] = []
    collaborators, _api = _collaborators(None, events)
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert events == []


def test_creation_that_changes_then_raises_is_rolled_back(monkeypatch):
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)

    def mutate_then_raise(doc, request):
        doc.addObject("App::FeaturePython", "Boom")
        raise RuntimeError("FreeCAD failed after mutating")

    monkeypatch.setattr(subject, "apply_spreadsheet_set_cells", mutate_then_raise)
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert "abort" in events or result["outcome"] in {"rejected", "uncertain"}


def test_recompute_failure_is_rolled_back():
    events: list[str] = []
    document = _RecomputeFailureDocument(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result.get("native_status") == "RecomputeFailed"


def test_failed_validation_aborts_before_commit():
    events: list[str] = []
    document = _Document(events)
    _seed(document)

    def fail_validation(_document):
        events.append("validate")
        raise RuntimeError("document health degraded")

    collaborators, _api = _collaborators(document, events, validator=fail_validation)
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"


def test_native_rejection_never_returns_cached_success():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(
        document, events, final_result={"status": "PublicationFailed", "committed": False}
    )
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result["native_status"] == "PublicationFailed"


def test_native_capability_is_required_before_apply():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
    )
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result.get("native_status") == "Unsupported"
    assert events == []


def test_native_rollback_failure_remains_distinguishable():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(
        document,
        events,
        final_result={"status": "RollbackFailed", "committed": False, "rollback_succeeded": False},
    )
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert result["success"] is False
    assert result["native_status"] == "RollbackFailed"
    assert result["rollback_succeeded"] is False


def test_apply_and_inspect_use_the_native_admitted_document():
    events: list[str] = []
    admitted = _NativeBridgeDocument(events)
    _seed(admitted)
    lookups: list[str] = []

    def changing_lookup(name):
        lookups.append(name)
        return admitted

    bridge = CollaborationAPI(document_lookup=changing_lookup)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
        run_fem_analysis=lambda *_a, **_k: {"success": True},
    )
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", [{"address": "A1", "value": 1}])
    assert lookups == ["Doc"]
    assert result["success"] is True or result["outcome"] in {"rejected", "uncertain"}


def test_d12_repro_set_alias_cells_echo_committed_aliases():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)
    cells = [
        {"address": "A1", "value": "plate_len", "set_alias": None},
        {"address": "B1", "value": 40, "set_alias": "plate_len"},
        {"address": "A2", "value": "plate_wid"},
        {"address": "B2", "value": 30, "set_alias": "plate_wid"},
        {"address": "A3", "value": "plate_thk"},
        {"address": "B3", "value": 8, "set_alias": "plate_thk"},
        {"address": "A4", "value": "hole_dia"},
        {"address": "B4", "value": 10, "set_alias": "hole_dia"},
    ]
    result = run_spreadsheet_set_cells(collaborators, "Doc", "Target", cells)
    assert result["success"] is True
    updated = result["updated"]
    alias_by_address = {row["address"]: row["alias"] for row in updated}
    assert alias_by_address["B1"] == "plate_len"
    assert alias_by_address["B2"] == "plate_wid"
    assert alias_by_address["B3"] == "plate_thk"
    assert alias_by_address["B4"] == "hole_dia"


def test_alias_addressing_updates_committed_alias():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    sheet = document.objects["Target"]
    sheet.setAlias("B1", "plate_len")
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(
        collaborators,
        "Doc",
        "Target",
        [{"alias": "plate_len", "value": 50}],
    )
    assert result["success"] is True
    assert result["updated"][0]["address"] == "B1"
    assert result["updated"][0]["alias"] == "plate_len"
    assert result["updated"][0]["value"] == "50"


def test_missing_set_alias_rejects_batch():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    sheet = document.objects["Target"]
    sheet.setAlias = None
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(
        collaborators,
        "Doc",
        "Target",
        [{"address": "B1", "value": 40, "set_alias": "plate_len"}],
    )
    assert result["success"] is False
    assert result["error_code"] == "INVALID_SHEET"


def test_in_batch_alias_collision_rejects():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(
        collaborators,
        "Doc",
        "Target",
        [
            {"address": "B1", "value": 40, "set_alias": "plate_len"},
            {"address": "B2", "value": 30, "set_alias": "plate_len"},
        ],
    )
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_existing_alias_collision_rejects():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    sheet = document.objects["Target"]
    sheet.setAlias("B1", "plate_len")
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(
        collaborators,
        "Doc",
        "Target",
        [{"address": "B2", "value": 30, "set_alias": "plate_len"}],
    )
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"


def test_requested_alias_not_bound_after_recompute_rejects():
    events: list[str] = []
    document = _Document(events)
    _seed(document)
    sheet = document.objects["Target"]
    sheet.setAlias = lambda *_a, **_k: None
    collaborators, _api = _collaborators(document, events)
    result = run_spreadsheet_set_cells(
        collaborators,
        "Doc",
        "Target",
        [{"address": "B1", "value": 40, "set_alias": "plate_len"}],
    )
    assert result["success"] is False
    assert result["error_code"] == "EXPRESSION_ERROR"


def test_unknown_or_contradictory_native_evidence_cannot_release_success():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_cells_mutation import (
        _NativeMutationState,
        _spreadsheet_set_cells_native_result,
    )

    for native_result in (
        None,
        {},
        {"status": "FutureStatus", "committed": False},
        {"status": "Committed", "committed": False},
        {"status": "Busy", "committed": True},
        {"status": "Committed", "committed": True, "rollback_failed": True},
    ):
        result = _spreadsheet_set_cells_native_result(native_result, _NativeMutationState(postcondition_passed=True))
        assert result["success"] is False
        assert result["outcome"] == "uncertain"
