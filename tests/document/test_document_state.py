from __future__ import annotations

from types import SimpleNamespace

import FreeCADGui
import pytest

from addon.FreeCADMCP.document_state import (
    DocumentDirtyStateUnavailable,
    document_modified_or_dirty,
    document_modified_state,
    mark_document_modified,
    require_document_modified,
    set_document_modified,
)


def test_app_proxy_modified_flag_remains_compatible(monkeypatch):
    monkeypatch.delattr(FreeCADGui, "getDocument", raising=False)
    document = SimpleNamespace(Name="Doc", Modified=True)

    assert document_modified_state(document) is True
    assert require_document_modified(document) is True


def test_gui_document_owns_authoritative_modified_flag(monkeypatch):
    gui_document = SimpleNamespace(Modified=True)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda name: gui_document if name == "Doc" else None,
        raising=False,
    )
    document = SimpleNamespace(Name="Doc", Modified=False, isTouched=lambda: False)

    # Gui::Document wins even if a compatibility App fake disagrees.
    assert document_modified_state(document) is True


def test_headless_touch_is_positive_only_and_unknown_clean_is_not_authoritative(
    monkeypatch,
):
    monkeypatch.delattr(FreeCADGui, "getDocument", raising=False)

    assert document_modified_state(
        SimpleNamespace(Name="Doc", isTouched=lambda: True)
    ) is True
    assert document_modified_state(
        SimpleNamespace(Name="Doc", isTouched=lambda: False)
    ) is None
    unknown = SimpleNamespace(Name="Doc", isTouched=lambda: False)
    assert document_modified_or_dirty(unknown) is True
    with pytest.raises(DocumentDirtyStateUnavailable):
        require_document_modified(unknown)


def test_mark_document_modified_sets_gui_proxy(monkeypatch):
    gui_document = SimpleNamespace(Modified=False)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: gui_document,
        raising=False,
    )
    document = SimpleNamespace(Name="Doc", Objects=[])

    assert mark_document_modified(document) is True
    assert gui_document.Modified is True


def test_set_document_modified_clears_gui_proxy(monkeypatch):
    gui_document = SimpleNamespace(Modified=True)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: gui_document,
        raising=False,
    )

    set_document_modified(SimpleNamespace(Name="Doc"), False)

    assert gui_document.Modified is False


def test_available_gui_with_missing_document_never_falls_back_to_app(monkeypatch):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    document = SimpleNamespace(Name="Doc", Modified=False)

    assert document_modified_state(document) is None
    assert document_modified_or_dirty(document) is True
    with pytest.raises(DocumentDirtyStateUnavailable):
        require_document_modified(document)
