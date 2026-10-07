"""B4 GUI smoke test – create an object via the addon, assert no DocumentWouldBlock.

This test is skipped in headless unit CI unless a live FreeCAD GUI instance
is already running (the ``requires_live_freecad_gui`` pytest marker).

Running the test requires FreeCADCmd/FreeCAD with a GUI event loop, the
``FreeCADMCP`` add-on loaded, and a document open.  Invoke it with::

    pytest tests/gui/test_collaboration_smoke.py -m requires_live_freecad_gui

The test verifies that ``commit_body_create_mutation`` (or the compatibility
variant) does *not* raise ``DocumentWouldBlock`` or return an error dict with
``"DocumentWouldBlock"`` when called from the FreeCAD GUI thread.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Skip this file entirely in headless CI.  The marker is declared in
# pyproject.toml; running without ``-m requires_live_freecad_gui`` leaves
# the test collected but skipped, so headless pipelines stay green.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.requires_live_freecad_gui


@pytest.fixture(scope="module")
def freecad_gui():
    """Import FreeCAD and FreeCADGui; skip unless a real GUI main window is up.

    Unit-test stubs can install ``FreeCAD``, ``FreeCADGui`` and ``PySide``
    (with any ``GuiUp`` value), so importability alone does not prove a live
    GUI.  A stub cannot return a genuine PySide ``QMainWindow``.
    """
    try:
        import FreeCAD
        import FreeCADGui
        from PySide import QtWidgets
    except ImportError:
        pytest.skip("FreeCAD GUI not available")
    try:
        main_window = FreeCADGui.getMainWindow()
    except Exception:  # noqa: BLE001
        main_window = None
    main_window_type = getattr(QtWidgets, "QMainWindow", None)
    if not isinstance(main_window_type, type) or not isinstance(
        main_window, main_window_type
    ):
        pytest.skip("FreeCAD GUI main window is not running")
    return FreeCAD


@pytest.fixture
def scratch_document(freecad_gui):
    """Create a temporary document and close it after the test."""
    doc = freecad_gui.newDocument("_B4SmokeTest")
    yield doc
    try:
        freecad_gui.closeDocument(doc.Name)
    except Exception:  # noqa: BLE001
        pass


def test_create_object_does_not_raise_document_would_block(
    scratch_document,
    monkeypatch,
) -> None:
    """commit_compatibility_mutation on the GUI thread must not block or raise.

    This smoke test forces *_is_freecad_gui_thread()* to report True (it
    should be True naturally when run inside FreeCAD's GUI event loop) and
    exercises the async path.  The mutation creates a plain Part::Feature so
    the test does not require the PartDesign workbench.

    The assertion is that the result is not an error dict whose "status"
    contains "WouldBlock" or "Blocked", and that no ``DocumentWouldBlock``
    exception is raised.
    """
    from addon.FreeCADMCP import collaboration_api as _api_mod

    # Ensure we are exercising the GUI-thread path regardless of whether the
    # test runner is actually on the Qt main thread.
    monkeypatch.setattr(_api_mod, "_is_freecad_gui_thread", lambda: True)

    api = _api_mod.CollaborationAPI(
        document_lookup=lambda name: scratch_document
    )

    created_objects: list[object] = []

    def apply_callback() -> None:
        obj = scratch_document.addObject("Part::Feature", "SmokeTestBox")
        created_objects.append(obj)

    # Use the general compatibility entry-point; structural=True so the lane
    # treats this as a full-document mutation.
    waiter = api.commit_compatibility_mutation(
        scratch_document.Name,
        apply_callback,
        structural=True,
    )

    # The waiter must be an _AsyncMutationWaiter because we forced GUI-thread
    # mode.  Await it (this unblocks as soon as the owner thread completes).
    assert hasattr(waiter, "await_result"), (
        f"Expected _AsyncMutationWaiter but got {type(waiter).__name__!r}; "
        "the async path was not taken"
    )
    result = waiter.await_result(timeout=30.0)

    # Verify the result is not a DocumentWouldBlock error.
    assert isinstance(result, dict), f"Expected dict result, got {type(result)}"
    status = result.get("status", "")
    assert "WouldBlock" not in str(status), (
        f"Mutation returned DocumentWouldBlock status: {result}"
    )
    assert "Blocked" not in str(status) or result.get("committed") is True, (
        f"Unexpected blocked status: {result}"
    )
    assert result.get("committed") is True or result.get("status") == "Committed", (
        f"Mutation did not commit successfully: {result}"
    )

    # At least one object should have been created.
    assert created_objects, "Callback was never invoked"
