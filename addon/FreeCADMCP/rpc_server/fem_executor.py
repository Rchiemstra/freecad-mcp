"""CalculiX-driven FEM analysis execution."""

from __future__ import annotations

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .fem_executor_ops.run_analysis import run_fem_analysis

__all__ = ["run_fem_analysis"]
