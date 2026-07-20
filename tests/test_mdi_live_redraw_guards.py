"""Unit tests for MDI live-redraw / Access-violation probe scoring.

These do not launch FreeCAD. They lock the pass/fail contract used by
``FreeCAD-dock-investigation/harness/mdi_viewport_probe.py`` so regressions in
scoring (e.g. treating post-release-only camera changes as live) are caught.
"""

from __future__ import annotations


def phase_camera_live(phase: dict) -> list[str]:
    """Return failure strings for rotate/pan gestures that did not change live."""
    failures: list[str] = []
    label = phase.get("label", "?")
    for key in ("rotate", "pan"):
        gesture = phase.get(key) or {}
        if not gesture.get("camera_changed_live"):
            failures.append(f"{label}.{key}: no live camera change")
        if gesture.get("exceptions"):
            failures.append(f"{label}.{key}: exceptions {gesture['exceptions'][:3]}")
    return failures


def log_access_violation_failures(log_counts: dict) -> list[str]:
    failures: list[str] = []
    av = int(log_counts.get("access_violation") or 0)
    notify = int(log_counts.get("notify_exception") or 0)
    if av or notify:
        failures.append(f"access_violation={av} notify_exception={notify}")
    return failures


def test_live_camera_change_is_required_for_rotate_and_pan():
    phase = {
        "label": "child_embedded",
        "rotate": {"camera_changed_live": True, "exceptions": []},
        "pan": {"camera_changed_live": True, "exceptions": []},
    }
    assert phase_camera_live(phase) == []


def test_missing_live_camera_is_a_failure():
    phase = {
        "label": "toplevel_detached",
        "rotate": {
            "camera_changed_live": False,
            "unique_cameras_during_drag": 1,
            "exceptions": [],
        },
        "pan": {"camera_changed_live": True, "exceptions": []},
    }
    failures = phase_camera_live(phase)
    assert failures == ["toplevel_detached.rotate: no live camera change"]


def test_gesture_exceptions_are_reported():
    phase = {
        "label": "maximized",
        "rotate": {
            "camera_changed_live": True,
            "exceptions": ["RuntimeError('viewer gone')"],
        },
        "pan": {"camera_changed_live": True, "exceptions": []},
    }
    failures = phase_camera_live(phase)
    assert any("exceptions" in item for item in failures)


def test_access_violation_log_counts_fail_the_run():
    assert log_access_violation_failures({"access_violation": 0, "notify_exception": 0}) == []
    failures = log_access_violation_failures({"access_violation": 55, "notify_exception": 1})
    assert failures == ["access_violation=55 notify_exception=1"]


def test_matrix_passes_only_when_every_phase_is_live_and_clean():
    phases = [
        {
            "label": "child_embedded",
            "rotate": {"camera_changed_live": True, "exceptions": []},
            "pan": {"camera_changed_live": True, "exceptions": []},
        },
        {
            "label": "reembedded_child",
            "rotate": {"camera_changed_live": True, "exceptions": []},
            "pan": {"camera_changed_live": True, "exceptions": []},
        },
    ]
    failures: list[str] = []
    for phase in phases:
        failures.extend(phase_camera_live(phase))
    failures.extend(log_access_violation_failures({"access_violation": 0, "notify_exception": 0}))
    assert failures == []
    assert not failures  # passed
