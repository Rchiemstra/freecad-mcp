"""Native commits name their undo step after the MCP method being served.

FreeCAD's Edit > Undo menu listed every MCP edit as "Collaborative operation
<uuid>". The native commit now takes a ``label``; a FreeCAD build without the
keyword is detected from its signature and committed unlabelled.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP import collaboration_api
from addon.FreeCADMCP.rpc_method_context import rpc_method_scope

pytestmark = pytest.mark.unit


def _labelled_commit(callback, *, structural=False, label=None):
    return label


def _legacy_commit(callback, *, structural=False):
    return None


def test_the_served_method_labels_a_supporting_commit():
    with rpc_method_scope("fillet_feature"):
        kwargs = collaboration_api._label_kwargs(_labelled_commit)

    assert kwargs == {"label": "MCP: fillet_feature"}
    assert _labelled_commit(lambda: None, **kwargs) == "MCP: fillet_feature"


def test_no_served_method_means_no_label():
    assert collaboration_api._label_kwargs(_labelled_commit) == {}


@pytest.mark.parametrize("commit", [_legacy_commit, len])
def test_a_commit_without_the_keyword_gets_no_label(commit):
    with rpc_method_scope("pad_feature"):
        assert collaboration_api._label_kwargs(commit) == {}


def test_the_method_scope_ends_with_its_block():
    with rpc_method_scope("pad_feature"):
        pass

    assert collaboration_api._label_kwargs(_labelled_commit) == {}
