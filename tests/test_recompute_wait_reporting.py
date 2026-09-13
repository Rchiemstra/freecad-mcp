"""``recompute_and_wait`` reports invoked / stabilized / still-touched apart.

One count cannot answer "did the recompute run?" and "did the document
settle?" at once, and in practice those disagree: a recompute that invokes
every feature and still leaves objects touched is a different failure from one
that never ran.  These contracts also pin the bounded, cycle-aware retry: a
dependency cycle is reported rather than retried, because forcing cannot
converge on one.
"""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.gui_tools_ops import recompute_wait

pytestmark = pytest.mark.unit


class FakeObject:
    def __init__(self, name, state=(), out_recursive=()):
        self.Name = name
        self.State = list(state)
        self._out_recursive = list(out_recursive)

    @property
    def OutListRecursive(self):
        return self._out_recursive

    def isValid(self):
        return "Invalid" not in self.State


class FakeDocument:
    def __init__(self, name, objects, plan=()):
        self.Name = name
        self.Objects = list(objects)
        self.calls = []
        self._plan = list(plan)

    def recompute(self, objs=None, force=False, *_rest):
        self.calls.append({"objs": objs, "force": bool(force)})
        if self._plan:
            self._plan.pop(0)(self)
        return len(self.Objects)

    def object(self, name):
        return next(obj for obj in self.Objects if obj.Name == name)


@pytest.fixture(autouse=True)
def _no_gui_flush(monkeypatch):
    monkeypatch.setattr(recompute_wait, "_flush_gui_events", lambda: None)


def _install(monkeypatch, document):
    monkeypatch.setattr(
        recompute_wait.FreeCAD,
        "getDocument",
        lambda name: document if name == document.Name else None,
        raising=False,
    )


def test_settled_recompute_separates_invoked_from_stabilized(monkeypatch):
    clean = FakeObject("Clean")
    dirty = FakeObject("Dirty", state=["Touched"])

    def settle(doc):
        doc.object("Dirty").State = ["Up-to-date"]

    document = FakeDocument("Doc", [clean, dirty], plan=[settle])
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Doc")

    assert payload["ok"] is True
    assert payload["settled"] is True
    # invoked answers "did it run", stabilized answers "what landed".
    assert payload["invoked"] == 2
    assert payload["recomputed_count"] == 2  # existing key preserved
    assert payload["touched_before"] == ["Dirty"]
    assert payload["stabilized"] == ["Dirty"]
    assert payload["pending_recompute"] == []
    assert payload["newly_touched"] == []
    assert payload["forced_passes"] == []
    assert payload["dependency_cycle"] == []
    # A settled document needs no forced pass at all.
    assert document.calls == [{"objs": None, "force": False}]


def test_a_recompute_that_runs_without_settling_is_not_reported_as_no_work(monkeypatch):
    stuck = FakeObject("Stuck", state=["Touched"])
    document = FakeDocument("Doc", [stuck])
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Doc")

    assert payload["invoked"] == 1
    assert payload["stabilized"] == []
    assert payload["pending_recompute"] == ["Stuck"]
    assert payload["settled"] is False
    # Forced retries are bounded, and stop as soon as one makes no progress.
    assert len(document.calls) == 2
    assert document.calls[1] == {"objs": None, "force": True}
    assert payload["forced_passes"] == [{"invoked": 1, "still_touched": ["Stuck"]}]


def test_forced_passes_continue_while_they_make_progress(monkeypatch):
    first = FakeObject("First", state=["Touched"])
    second = FakeObject("Second", state=["Touched"])
    third = FakeObject("Third", state=["Touched"])

    def clear(name):
        def step(doc):
            doc.object(name).State = ["Up-to-date"]

        return step

    document = FakeDocument(
        "Doc", [first, second, third], plan=[clear("First"), clear("Second")]
    )
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Doc")

    # "First" settled on the plain pass, "Second" on the first forced pass.
    assert payload["stabilized"] == ["First", "Second"]
    assert payload["pending_recompute"] == ["Third"]
    assert all(call["force"] for call in document.calls[1:])
    # The first forced pass shrank the set, so a second was worth trying; the
    # second made no progress and ended the retry.
    assert payload["forced_passes"] == [
        {"invoked": 3, "still_touched": ["Third"]},
        {"invoked": 3, "still_touched": ["Third"]},
    ]
    assert len(document.calls) == 1 + len(payload["forced_passes"])


def test_a_dependency_cycle_is_reported_instead_of_retried(monkeypatch):
    looping = FakeObject("Loop", state=["Touched"])
    looping._out_recursive = [looping]
    document = FakeDocument("Doc", [looping])
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Doc")

    assert payload["dependency_cycle"] == ["Loop"]
    assert payload["pending_recompute"] == ["Loop"]
    assert payload["settled"] is False
    # Forcing cannot converge on a cycle, so no forced pass is attempted.
    assert document.calls == [{"objs": None, "force": False}]
    assert payload["forced_passes"] == []


def test_objects_touched_by_the_recompute_itself_are_reported_separately(monkeypatch):
    quiet = FakeObject("Quiet")
    trigger = FakeObject("Trigger", state=["Touched"])

    def side_effect(doc):
        doc.object("Trigger").State = ["Up-to-date"]
        doc.object("Quiet").State = ["Touched"]

    document = FakeDocument("Doc", [quiet, trigger], plan=[side_effect])
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Doc")

    assert payload["stabilized"] == ["Trigger"]
    assert payload["newly_touched"] == ["Quiet"]


def test_missing_document_still_reports_the_original_shape(monkeypatch):
    document = FakeDocument("Doc", [])
    _install(monkeypatch, document)

    payload = recompute_wait.recompute_and_wait("Absent")

    assert payload == {"ok": False, "error": "Document not found: Absent"}
