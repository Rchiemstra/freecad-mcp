"""Architecture policy: Part 3 checked-edit RPCs must not use lease DocumentSelector."""

from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.unit


def test_part3_collaboration_methods_do_not_import_lease_document_selector() -> None:
    from addon.FreeCADMCP.rpc_server.methods import part3_collaboration_methods

    source = inspect.getsource(part3_collaboration_methods)
    assert "document_lease.types.document_selector" not in source
    assert "DocumentSelector" not in source
