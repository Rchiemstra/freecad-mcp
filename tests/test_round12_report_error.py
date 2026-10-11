from types import SimpleNamespace as NS
import pytest
from freecad_mcp.operations.interactive import get_report_view_operation

pytestmark = pytest.mark.unit


def test_report_success_returns_result():
    assert get_report_view_operation(NS(get_report_view=lambda **kw: {'ok':True,'text':'new'})) is not None


def test_modal_failure_returns_structured_tool_error():
    result = get_report_view_operation(NS(get_report_view=lambda **kw: {
        'ok':False,'error_code':'GUI_BLOCKED_BY_MODAL_DIALOG','error':'GUI blocked by modal dialog: Test', 'retry_safe':True}))
    assert result.isError
    assert 'GUI_BLOCKED_BY_MODAL_DIALOG' in str(result)
