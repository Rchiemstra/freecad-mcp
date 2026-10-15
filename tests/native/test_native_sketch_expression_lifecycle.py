"""Round 28 qualification at the real Sketcher/native-commit boundary."""
import pytest

from tests.native.test_native_clear_expression import _collaborators, _require_native_collaboration

pytestmark = pytest.mark.core


@pytest.mark.parametrize("mode", ["open", "reopen", "closed"],
                         ids=["happy_open", "source_reopened", "defect_clear_closed"])
def test_native_constraint_source_repair(tmp_path, mode):
    _require_native_collaboration()
    import FreeCAD as App
    import Part
    import Sketcher
    from addon.FreeCADMCP.rpc_method_context import rpc_method_scope
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.clear_expression import run_clear_expression
    from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import validate_document_invariants

    source = App.newDocument("SrcDoc")
    dependent = App.newDocument("DepDoc")
    try:
        sheet = source.addObject("Spreadsheet::Sheet", "Dims")
        for address, value, alias in (("A1", "12", "PadLen"), ("A2", "30", "Wall")):
            sheet.set(address, value)
            sheet.setAlias(address, alias)
        source.recompute()
        source.saveAs(str(tmp_path / "SrcDoc.FCStd"))
        sk = dependent.addObject("Sketcher::SketchObject", "Sketch")
        for end, value, name in ((App.Vector(30, 0, 0), 30, "W"), (App.Vector(0, 12, 0), 12, "H")):
            geo = sk.addGeometry(Part.LineSegment(App.Vector(), end))
            constraint = sk.addConstraint(Sketcher.Constraint("Distance", geo, value))
            sk.renameConstraint(constraint, name)
        dependent.saveAs(str(tmp_path / "DepDoc.FCStd"))
        sk.setExpression("Constraints[0]", "SrcDoc#<<Dims>>.Wall")
        sk.setExpression("Constraints.H", "SrcDoc#<<Dims>>.PadLen")
        dependent.recompute()
        dependent.save()
        if mode != "open":
            App.closeDocument("SrcDoc")
        if mode == "reopen":
            source = App.openDocument(str(tmp_path / "SrcDoc.FCStd"))
            dependent.recompute()
            assert "Invalid" not in sk.State
            source.Dims.set("A2", "42")
            source.recompute()
            dependent.recompute()
            assert sk.getDatum(0).Value == 42
        with rpc_method_scope("clear_expression"):
            result = run_clear_expression(_collaborators(App, validate_document_invariants),
                                          "DepDoc", "Sketch", "Constraints.W")
        assert result["success"] is True, result
        assert [p for p, _ in sk.ExpressionEngine] == [".Constraints.H"]
        dependent.undo()
        assert len(sk.ExpressionEngine) == 2
        dependent.redo()
        assert [p for p, _ in sk.ExpressionEngine] == [".Constraints.H"]
    finally:
        App.closeDocument("DepDoc")
        if "SrcDoc" in App.listDocuments():
            App.closeDocument("SrcDoc")
