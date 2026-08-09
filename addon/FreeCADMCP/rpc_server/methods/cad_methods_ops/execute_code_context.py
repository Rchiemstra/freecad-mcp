"""execute_code routing policy helpers (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...telemetry import emit as emit_telemetry


def build_execute_code_context(
    code: str,
    options: dict[str, Any],
    *,
    analyze_execute_code_fn: Callable[..., dict[str, Any]],
    typed_tool_warning_fn: Callable[..., Any],
) -> tuple[str, dict[str, Any], Callable[[dict[str, Any]], dict[str, Any]] | None]:
    generated_operation = bool(options.get("generated_operation"))
    analysis = analyze_execute_code_fn(code, options)
    category = (
        "generated_internal_execute"
        if generated_operation
        else "read_only_worker_analysis"
        if options.get("read_only")
        else "public_execute_code"
    )
    warning = None if generated_operation else typed_tool_warning_fn(analysis)
    emit_telemetry(
        "execute_code",
        "routing_completed",
        payload={
            "execution_category": category,
            "analysis": analysis,
            "typed_tool_available": bool(warning),
        },
    )

    def annotate(payload):
        if not isinstance(payload, dict):
            return payload
        annotated = dict(payload)
        annotated["execution_category"] = category
        annotated["code_analysis"] = analysis
        annotated.setdefault(
            "mutation_scope",
            {
                "declared_documents": analysis["document_scope"],
                "transaction_coverage": "unavailable",
                "rollback_policy": "none",
            },
        )
        if warning is not None:
            annotated.setdefault("warnings", []).append(warning)
        return annotated

    return category, analysis, annotate
