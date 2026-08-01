"""Privacy-preserving AST classification for public ``execute_code`` calls."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .execute_code_analysis_ops.analyze import analyze_execute_code
from .execute_code_analysis_ops.typed_tool_warning import typed_tool_warning

__all__ = ["analyze_execute_code", "typed_tool_warning"]
