"""Unit tests for snapshot link identity grouping (no FreeCAD required)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.worker_entry import (
    ExternalLinkUnresolved,
    _group_expected_link_entries,
    _manifest_identity,
    _validate_property_group_pre_recompute,
)


def _row(
    *,
    owner_document="Doc",
    owner_object="Holder",
    property_name="Supports",
    target_document="Doc",
    target_object="Box",
    subelements,
):
    return {
        "owner_document": owner_document,
        "owner_object": owner_object,
        "property": property_name,
        "property_type": "App::PropertyLinkSubList",
        "target_document": target_document,
        "target_object": target_object,
        "subelements": list(subelements),
    }


def _target(doc_name: str, name: str):
    return SimpleNamespace(Document=SimpleNamespace(Name=doc_name), Name=name)


@pytest.mark.unit
def test_group_expected_links_preserves_manifest_order_within_property():
    rows = [
        _row(subelements=["Face1"], target_object="Box"),
        _row(subelements=["Face2"], target_object="Box2"),
        _row(subelements=["Face1"], target_object="Box"),
        _row(subelements=["Face3"], property_name="Other"),
    ]
    grouped = _group_expected_link_entries(rows)
    assert [key[2] for key, _items in grouped] == ["Supports", "Other"]
    assert len(grouped[0][1]) == 3
    assert grouped[1][1][0]["subelements"] == ["Face3"]


@pytest.mark.unit
def test_pre_recompute_rejects_duplicate_manifest_without_matching_third_entry(
    monkeypatch,
):
    box = _target("Doc", "Box")
    box2 = _target("Doc", "Box2")
    refs = [(box, ["Face1"]), (box2, ["Face2"])]
    rows = [
        _row(subelements=["Face1"]),
        _row(subelements=["Face2"], target_object="Box2"),
        _row(subelements=["Face1"]),
    ]

    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.worker_entry._read_property_reference_entries",
        lambda *_args, **_kwargs: (refs, "Doc.Holder.Supports"),
    )
    with pytest.raises(ExternalLinkUnresolved):
        _validate_property_group_pre_recompute(
            rows,
            {"link_policy": "strict", "ignored_links": []},
            property_key=("Doc", "Holder", "Supports"),
        )


@pytest.mark.unit
def test_pre_recompute_anchors_distinct_indexes_for_separated_duplicates(monkeypatch):
    box = _target("Doc", "Box")
    box2 = _target("Doc", "Box2")
    refs = [(box, ["Face1"]), (box2, ["Face2"]), (box, ["Face1"])]
    rows = [
        _row(subelements=["Face1"]),
        _row(subelements=["Face2"], target_object="Box2"),
        _row(subelements=["Face1"]),
    ]
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.worker_entry._read_property_reference_entries",
        lambda *_args, **_kwargs: (refs, "Doc.Holder.Supports"),
    )
    anchors = _validate_property_group_pre_recompute(
        rows,
        {"link_policy": "strict", "ignored_links": []},
        property_key=("Doc", "Holder", "Supports"),
    )
    assert [item["ref_index"] for item in anchors] == [0, 1, 2]
    assert [_manifest_identity(item["expected"]) for item in anchors] == [
        _manifest_identity(row) for row in rows
    ]
