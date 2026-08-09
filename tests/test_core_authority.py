"""Unit tests for the FreeCAD core mutation-authority bridge."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.document_lease import core_authority


class _FakeDoc:
    def __init__(self, *, has_api: bool = True):
        self.Name = "Doc"
        self._has_api = has_api
        self.owner_calls: list[tuple] = []
        self.capability_calls: list[tuple] = []
        self.cleared = 0
        self.takeovers = 0
        self._status = {
            "owner": "unrestricted",
            "generation": 0,
            "provider_id": "",
            "restricted": False,
        }

    def setMutationOwner(self, mode, generation=0, provider_id=""):
        if not self._has_api:
            raise AttributeError("missing")
        self.owner_calls.append((mode, generation, provider_id))
        self._status = {
            "owner": mode,
            "generation": int(generation),
            "provider_id": provider_id,
            "restricted": mode == "mcp",
        }

    def clearMutationOwner(self):
        self.cleared += 1
        self._status = {
            "owner": "unrestricted",
            "generation": 0,
            "provider_id": "",
            "restricted": False,
        }

    def openMutationCapability(self, kinds=None, generation=0):
        if not self._has_api:
            raise AttributeError("missing")
        self.capability_calls.append((tuple(kinds or ()), int(generation)))
        return {"kinds": kinds, "generation": generation}

    def bumpMutationGeneration(self):
        self.takeovers += 1
        self._status["owner"] = "user"
        self._status["generation"] = int(self._status["generation"]) + 1
        self._status["restricted"] = False
        return self._status["generation"]

    def mutationAuthorityStatus(self):
        return dict(self._status)


def test_core_authority_available_detects_api():
    assert core_authority.core_authority_available(_FakeDoc()) is True
    assert core_authority.core_authority_available(SimpleNamespace()) is False


def test_set_and_clear_owner_soft_compat():
    doc = _FakeDoc()
    assert core_authority.set_mcp_owner(doc, generation=3, provider_id="agent-1")
    assert doc.owner_calls == [("mcp", 3, "agent-1")]
    assert core_authority.clear_owner(doc)
    assert doc.cleared == 1

    stock = SimpleNamespace(Name="Stock")
    assert core_authority.set_mcp_owner(stock, generation=1) is False
    assert core_authority.clear_owner(stock) is False


def test_open_mutation_capability_holds_capsule_until_exit():
    doc = _FakeDoc()
    with core_authority.open_mutation_capability(
        doc, generation=7, kinds=("AddObject", "PropertyWrite")
    ) as capsule:
        assert capsule is not None
        assert doc.capability_calls == [(("AddObject", "PropertyWrite"), 7)]


def test_open_mutation_capability_soft_compat_without_api():
    stock = SimpleNamespace(Name="Stock")
    with core_authority.open_mutation_capability(stock, generation=1) as capsule:
        assert capsule is None


def test_kinds_for_rpc_method():
    assert "Save" in core_authority.kinds_for_rpc_method("save_document", "save")
    assert "Close" in core_authority.kinds_for_rpc_method("close_document", "close")
    assert core_authority.kinds_for_rpc_method("ping", "read_only") == ()
    assert "AddObject" in core_authority.kinds_for_rpc_method(
        "create_object", "live_mutation"
    )
    assert "StructuralProperty" in core_authority.LIVE_MUTATION_KINDS


def test_sync_gui_lease_takeover_without_service_returns_true():
    doc = _FakeDoc()
    # No FreeCADMCP runtime service in unit tests → soft success.
    assert core_authority.sync_gui_lease_takeover(doc) is True


def test_sync_owner_from_lease_record_and_takeover():
    doc = _FakeDoc()
    record = SimpleNamespace(
        generation=11,
        state=SimpleNamespace(value="LOCKED_IDLE"),
        owner=SimpleNamespace(mcp_instance_id="inst-9", agent_id="a"),
    )
    assert core_authority.sync_owner_from_lease_record(doc, record)
    assert doc.owner_calls[-1][0] == "mcp"
    assert doc.owner_calls[-1][1] == 11

    intervened = SimpleNamespace(
        generation=12,
        state=SimpleNamespace(value="USER_INTERVENED"),
        owner=None,
    )
    assert core_authority.sync_owner_from_lease_record(doc, intervened)
    assert doc.takeovers == 1


def test_open_documents_mutation_capability_multi_doc():
    a = _FakeDoc()
    a.Name = "A"
    b = _FakeDoc()
    b.Name = "B"
    with core_authority.open_documents_mutation_capability(
        [a, b],
        generations={"A": 1, "B": 2},
        kinds=("AddObject",),
    ) as capsules:
        assert len(capsules) == 2
        assert a.capability_calls[0][1] == 1
        assert b.capability_calls[0][1] == 2


def test_observer_path_still_importable_without_core():
    """Stock FreeCAD soft-compat: importing observer helpers must not require core."""

    from addon.FreeCADMCP.document_lease import observer

    assert hasattr(observer, "register_observer")
