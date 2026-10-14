from types import SimpleNamespace as NS
import pytest
from tests.spreadsheet.test_spreadsheet_set_cells import _item
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_set_cells import run_spreadsheet_set_cells

pytestmark = pytest.mark.unit
REFUSAL = 'generic recompute has an unresolved cross-document dependency; recompute the document directly, outside this collaborative commit'


@pytest.mark.parametrize('cross', [False, True], ids=['happy_local', 'defect_external'])
def test_cell_formula_commits_and_evaluates(cross):
    sheet = _item('Bridge', type_id='Spreadsheet::Sheet')
    sheet.get = lambda address: getattr(sheet, address)
    formula = '=SrcDoc#<<Dims>>.PadLen' if cross else '=25'
    calls = []
    doc = NS(Name='MidDoc', getObject=lambda name: sheet, recompute=lambda: setattr(sheet, 'B1', 25))
    def commit(name, apply, post, *, structural=True, recompute=True):
        calls.append(recompute)
        apply(doc)
        if cross and recompute:
            sheet.set('B1', '')
            return dict(status='RecomputeFailed', committed=False, message=REFUSAL, rollback_succeeded=True)
        if recompute:
            doc.recompute()
        assert post(doc)
        return dict(status='Committed', committed=True)
    result = run_spreadsheet_set_cells(NS(commit_native_mutation=commit, validate_document_invariants=lambda doc: None),
                                      'MidDoc', 'Bridge', [{'address': 'B1', 'value': formula, 'alias': 'BridgedLen'}])
    assert result['success'], result
    assert sheet.getContents('B1') == formula
    assert sheet.B1 == 25
    assert result['updated'][0]['value'] == 25
    assert calls == ([True, False] if cross else [True])


@pytest.mark.parametrize('terminal', [
    dict(status='RollbackFailed', committed=False, rollback_failed=True),
    dict(status='RecomputeFailed', committed=None),
    dict(status='ApplyFailed', committed=False, rollback_succeeded=True),
])
def test_uncertain_or_unrelated_failure_never_reapplies(terminal):
    calls = []
    def commit(*args, **kwargs):
        calls.append(kwargs)
        return dict(message=REFUSAL, **terminal)
    result = run_spreadsheet_set_cells(NS(commit_native_mutation=commit, validate_document_invariants=lambda doc: None),
                                      'MidDoc', 'Bridge', [{'address': 'B1', 'value': '=SrcDoc#Dims.PadLen'}])
    assert not result['success']
    assert len(calls) == 1


def test_failed_direct_evaluation_reports_committed_repairable_formula():
    sheet = _item('Bridge', type_id='Spreadsheet::Sheet')
    calls = []
    def recompute():
        raise RuntimeError('source unavailable')
    doc = NS(Name='MidDoc', getObject=lambda name: sheet, recompute=recompute)
    def commit(name, apply, post, *, structural=True, recompute=True):
        calls.append(recompute)
        apply(doc)
        if recompute:
            return dict(status='RecomputeFailed', committed=False, message=REFUSAL, rollback_succeeded=True)
        assert post(doc)
        return dict(status='Committed', committed=True)
    result = run_spreadsheet_set_cells(NS(commit_native_mutation=commit, validate_document_invariants=lambda doc: None),
                                      'MidDoc', 'Bridge', [{'address': 'B1', 'value': '=SrcDoc#Dims.PadLen'}])
    assert result['success'] is False
    assert result['committed'] is True
    assert result['error_code'] == 'SPREADSHEET_RECOMPUTE_FAILED'
    assert sheet.getContents('B1') == '=SrcDoc#Dims.PadLen'
    assert calls == [True, False]
