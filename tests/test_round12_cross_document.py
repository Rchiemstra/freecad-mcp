from types import SimpleNamespace as NS
import pytest
from tests.set.test_set_expression import _item
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_expression import run_set_expression
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.execute_code_response import finalize_gui_execute_response

pytestmark = pytest.mark.unit
REFUSAL = 'generic recompute has an unresolved cross-document dependency; recompute the document directly, outside this collaborative commit'


def binding(cross):
    obj = _item("Box")
    doc = NS(Name="Dst", getObject=lambda name: obj, recompute=lambda: setattr(obj, "Length", 25))
    calls = []
    def commit(name, apply, post, *, structural=True, recompute=True):
        calls.append(recompute)
        apply(doc)
        if cross and recompute:
            obj.clearExpression("Length")
            return dict(status="RecomputeFailed", committed=False, message=REFUSAL)
        assert post(doc)
        return dict(status="Committed", committed=True)
    collab = NS(commit_native_mutation=commit, validate_document_invariants=lambda doc: None)
    return run_set_expression(collab, "Dst", "Box", "Length", "Src#Box.Length" if cross else "25"), obj, calls


def test_local_binding_stays_one_commit():
    result, obj, calls = binding(False)
    assert result["success"]
    assert calls == [True]


def test_cross_document_binding_commits_then_recomputes_directly():
    result, obj, calls = binding(True)
    assert result["success"]
    assert obj.getExpression("Length") == "Src#Box.Length"
    assert obj.Length == 25
    assert result["bound_value"] == "25"
    assert calls == [True, False]


def test_execute_code_refusal_names_tools():
    result = finalize_gui_execute_response(lambda v: v, {"ok": False, "error": REFUSAL}, {"document": "Dst"})
    assert 'recompute="none"' in result["error"]
    assert 'recompute_document' in result["error"]


def test_unsaved_link_names_source_document():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_expression import apply_set_expression, build_set_expression_request
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.set_expression_mutation import SetExpressionError
    obj = _item('Box')
    def unsaved(*args):
        raise RuntimeError('Linked document not saved')
    obj.setExpression = unsaved
    doc = NS(getObject=lambda name:obj)
    request = build_set_expression_request('Dst', 'Box', 'Length', 'Src#Box.Length')
    with pytest.raises(SetExpressionError, match="save linked document 'Src'.*save_document_as"):
        apply_set_expression(doc, request)


def test_failed_direct_recompute_keeps_committed_binding():
    obj = _item('Box')
    def fail_recompute():
        raise RuntimeError('external source unavailable')
    doc = NS(getObject=lambda name:obj, recompute=fail_recompute)
    def commit(name, apply, post, *, structural=True, recompute=True):
        apply(doc)
        if recompute:
            return dict(status='RecomputeFailed', committed=False, message=REFUSAL)
        assert post(doc)
        return dict(status='Committed', committed=True)
    result = run_set_expression(NS(commit_native_mutation=commit, validate_document_invariants=lambda doc:None),
                                'Dst','Box','Length','Src#Box.Length')
    assert not result['success']
    assert result['committed'] is True
    assert result['error_code'] == 'EXPRESSION_RECOMPUTE_FAILED'
    assert obj.getExpression('Length') == 'Src#Box.Length'


def test_cross_document_sketch_datum_reports_bound_value():
    obj = _item('Sketch')
    obj.Constraints = [NS(Type='Distance', Name='Height')]
    obj.getDatum = lambda index:25
    doc = NS(getObject=lambda name:obj, recompute=lambda:None)
    def commit(name, apply, post, *, structural=True, recompute=True):
        apply(doc)
        if recompute:
            return dict(status='RecomputeFailed', committed=False, message=REFUSAL)
        assert post(doc)
        return dict(status='Committed', committed=True)
    result = run_set_expression(NS(commit_native_mutation=commit, validate_document_invariants=lambda doc:None),
                                'Dst','Sketch','Constraints[0]','Src#Box.Length')
    assert result['success']
    assert result['bound_value'] == '25'


@pytest.mark.parametrize('prop_path', ['Constraints[0]', '.Constraints.Height'])
def test_cross_document_sketch_datum_with_copied_constraint_wrappers(prop_path):
    class Sketch(NS):
        @property
        def Constraints(self):
            # PropertyConstraintList and Constraint::getPyObject create fresh
            # copied wrappers on every property read in real FreeCAD.
            return [NS(Type='Distance', Name='Height')]

    obj = Sketch(**vars(_item('Sketch')))
    obj.PropertiesList = ['Constraints']
    obj.getDatum = lambda index: 25 if index == 0 else pytest.fail('wrong datum index')
    assert obj.Constraints[0] is not obj.Constraints[0]
    doc = NS(getObject=lambda name: obj, recompute=lambda: None)
    calls = []

    def commit(name, apply, post, *, structural=True, recompute=True):
        calls.append(recompute)
        apply(doc)
        if recompute:
            obj.clearExpression(prop_path)
            return dict(status='RecomputeFailed', committed=False, message=REFUSAL)
        assert post(doc)
        return dict(status='Committed', committed=True)

    result = run_set_expression(
        NS(commit_native_mutation=commit, validate_document_invariants=lambda doc: None),
        'Dst', 'Sketch', prop_path, 'Src#Box.Length',
    )
    assert result['success'], result
    assert result['bound_value'] == '25'
    assert obj.getExpression(prop_path) == 'Src#Box.Length'
    assert calls == [True, False]
