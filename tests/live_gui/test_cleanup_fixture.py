"""Exercise pytest report-driven recovery without launching FreeCAD."""

import os
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("phase", ["setup", "call"])
def test_failed_test_closes_documents_and_reuses_session(pytester, monkeypatch, phase):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(root), str(root / "src"))))
    pytester.makeconftest("""
import json
from types import SimpleNamespace
import pytest
from tests.live_gui import conftest as live
from tests.live_gui._support import ToolResult

mcp = live.mcp
pytest_runtest_makereport = live.pytest_runtest_makereport
live._check_for_death = lambda session, item: False

class Client:
    gui_request_timed_out = False
    def __init__(self):
        self.documents = []
        self.closed = []
    def call(self, tool, **args):
        if tool == 'create_document':
            self.documents.append(args['name'])
        elif tool == 'close_document':
            self.documents.remove(args['doc_name'])
            self.closed.append(args['doc_name'])
        else:
            assert tool == 'list_documents'
        return ToolResult(tool, False, json.dumps(self.documents), {})

@pytest.fixture(scope='session')
def _live_gui_session():
    client = Client()
    return SimpleNamespace(client=client, gui=object(), original_client=client, abort_message=None)

@pytest.fixture
def live_gui(_live_gui_session):
    return _live_gui_session.gui
""")
    pytester.makepyfile(f"""
import pytest

@pytest.fixture
def fail_setup(mcp):
    if {phase!r} == 'setup':
        mcp.call('create_document', name='LiveAttach')
        raise AssertionError('forced setup failure')

def test_01_forced_failure(mcp, fail_setup):
    mcp.call('create_document', name='LiveAttach')
    raise AssertionError('forced call failure')

def test_02_session_has_no_cascade(mcp, live_gui, _live_gui_session):
    assert mcp.documents == []
    assert mcp.closed == ['LiveAttach']
    assert mcp is _live_gui_session.original_client
    assert live_gui is _live_gui_session.gui
""")
    result = pytester.runpytest_subprocess("-q", "-p", "no:cacheprovider")
    result.assert_outcomes(passed=1, failed=int(phase == "call"), errors=int(phase == "setup"))
