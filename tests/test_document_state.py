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
from addon.FreeCADMCP.lock_indicator_ops.local_recovery import (
    _local_recovery_capabilities,
)


def test_app_proxy_modified_flag_remains_compatible(monkeypatch):
    monkeypatch.delattr(FreeCADGui, "getDocument", raising=False)
    document = SimpleNamespace(Name="Doc", Modified=True)

    assert document_modified_state(document) is True
    assert require_document_modified(document) is True


def test_legacy_gui_document_owns_modified_flag_when_app_api_is_absent(monkeypatch):
    gui_document = SimpleNamespace(Modified=True)
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda name: gui_document if name == "Doc" else None,
        raising=False,
    )
    document = SimpleNamespace(Name="Doc", Modified=False, isTouched=lambda: False)

    # On an older runtime Gui::Document wins over a compatibility App fake.
    assert document_modified_state(document) is True


def test_native_app_file_change_state_wins_when_headless_gui_document_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    document = SimpleNamespace(
        Name="Doc",
        getFileChangeState=lambda: {
            "state": "modified",
            "has_pending_file_changes": True,
            "last_canonical_save_failed": False,
        },
    )

    assert document_modified_state(document) is True
    assert require_document_modified(document) is True


def test_native_app_save_failure_overlay_is_part_of_modified_state(monkeypatch):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: SimpleNamespace(Modified=False),
        raising=False,
    )
    document = SimpleNamespace(
        Name="Doc",
        getFileChangeState=lambda: {
            "state": "clean",
            "has_pending_file_changes": False,
            "last_canonical_save_failed": True,
        },
    )

    assert document_modified_state(document) is True


def test_unreadable_native_app_state_does_not_fall_back_to_gui(monkeypatch):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: SimpleNamespace(Modified=False),
        raising=False,
    )
    document = SimpleNamespace(Name="Doc", getFileChangeState=lambda: {})

    assert document_modified_state(document) is None
    with pytest.raises(DocumentDirtyStateUnavailable):
        require_document_modified(document)


def test_native_app_clean_state_is_not_overridden_by_touch_only_fallback(monkeypatch):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    touched = []
    document = SimpleNamespace(
        Name="Doc",
        getFileChangeState=lambda: {
            "state": "clean",
            "has_pending_file_changes": False,
            "last_canonical_save_failed": False,
        },
        Objects=[SimpleNamespace(touch=lambda: touched.append(True))],
        isTouched=lambda: bool(touched),
    )

    assert mark_document_modified(document) is False
    assert touched == [True]
    assert document_modified_state(document) is False


def test_local_recovery_uses_app_only_dirty_state(monkeypatch):
    monkeypatch.setattr(
        FreeCADGui,
        "getDocument",
        lambda _name: None,
        raising=False,
    )
    document = SimpleNamespace(
        Name="Doc",
        Modified=False,
        getFileChangeState=lambda: {
            "state": "modified",
            "has_pending_file_changes": True,
            "last_canonical_save_failed": False,
        },
    )
    lease = {
        "schema_version": 2,
        "source": "local",
        "document": {
            "session_uuid": "session-1",
            "canonical_path": "C:/work/Doc.FCStd",
        },
        "lease": {"state": "USER_INTERVENED"},
        "document_state": {},
    }

    assert _local_recovery_capabilities(lease, document)["keep_dirty"] is True


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
