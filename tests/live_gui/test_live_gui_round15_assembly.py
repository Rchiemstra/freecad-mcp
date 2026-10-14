"""Contradictory fixed and distance constraints must not solve successfully."""
import pytest
from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload

pytestmark = pytest.mark.live_gui


def _assembly(mcp, doc):
    assert_ok(mcp.call('create_document', name=doc))
    assert_ok(mcp.call('execute_code', document=doc, recompute='target', execution_mode='gui',
                       code="import FreeCAD\nd=FreeCAD.getDocument(%r)\na=d.addObject('Part::Box','A');a.Length=20;a.Width=10;a.Height=5\nb=d.addObject('Part::Box','B');b.Length=15;b.Width=8;b.Height=4;b.Placement.Base=FreeCAD.Vector(30,0,0)" % doc))
    assert_ok(mcp.call('create_assembly', doc_name=doc, assembly_name='Asm'))
    for name in ('A', 'B'):
        assert_ok(mcp.call('move_object', doc_name=doc, obj_name=name, target_container='Asm'))
    assert_ok(mcp.call('create_assembly_grounded_joint', doc_name=doc, assembly_name='Asm', component_name='A'))
    assert_ok(mcp.call('create_assembly_joint', doc_name=doc, assembly_name='Asm', joint_type='Fixed',
                       ref1_component='A', ref2_component='B', ref1_element='Face1', ref2_element='Face1'))


def test_fixed_assembly_solves(mcp, gui_log):
    doc = 'R15FixedGood'
    _assembly(mcp, doc)
    result = _payload(assert_ok(mcp.call('solve_assembly', doc_name=doc, assembly_name='Asm')))
    assert result['solver_status'] == '0'
    assert_ok(mcp.call('close_document', doc_name=doc))
    assert_clean(gui_log)


def test_fixed_distance_contradiction_is_rejected(mcp, gui_log):
    doc = 'R15FixedConflict'
    _assembly(mcp, doc)
    assert_ok(mcp.call('create_assembly_joint', doc_name=doc, assembly_name='Asm', joint_type='Distance',
                       ref1_component='A', ref2_component='B', ref1_element='Face1', ref2_element='Face1',
                       properties={'Distance': 100}))
    result = mcp.call('solve_assembly', doc_name=doc, assembly_name='Asm')
    assert_ok(mcp.call('get_objects', doc_name=doc, fields=['Name']))
    assert result.is_error, result.text
    assert _payload(result)['error_code'] == 'ASSEMBLY_SOLVE_FAILED'
    assert_ok(mcp.call('close_document', doc_name=doc))
    assert_clean(gui_log, r"Assembly solve: joint '.*' does not hold")
