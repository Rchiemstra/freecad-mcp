"""FreeCADConnection method implementations."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("FreeCADMCPserver")



def sketch_attach(
        conn,
        doc_name: str,
        sketch_name: str,
        support,
        attachment_offset: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "support": support,
        }
        # Omit the key entirely for older add-on method signatures.
        if attachment_offset is not None:
            params["attachment_offset"] = attachment_offset
        routed = conn._invoke_mutation_v2(
            "sketch_attach",
            params,
            document_names=(doc_name,),
            operation_name="Attach sketch",
        )
        if routed is not None:
            return routed
        # Compatibility: do not pass a fourth positional arg when unused.
        if attachment_offset is not None:
            return conn.server.sketch_attach(
                doc_name, sketch_name, support, attachment_offset
            )
        return conn.server.sketch_attach(doc_name, sketch_name, support)


def sketch_edit_constraint(
        conn,
        doc_name: str,
        sketch_name: str,
        value: float | None = None,
        name: str | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        routed = conn._invoke_mutation_v2(
            "sketch_edit_constraint",
            {
                "doc_name": doc_name,
                "sketch_name": sketch_name,
                "value": value,
                "name": name,
                "index": index,
            },
            document_names=(doc_name,),
            operation_name="Edit sketch constraint",
        )
        if routed is not None:
            return routed
        return conn.server.sketch_edit_constraint(
            doc_name, sketch_name, value, name, index
        )


def diagnose_parametric(
        conn, doc_name: str, object_name: str | None = None
    ) -> dict[str, Any]:
        return conn.server.diagnose_parametric(doc_name, object_name)


def recompute_document(conn, doc_name: str) -> dict[str, Any]:
        routed = conn._invoke_mutation_v2(
            "recompute_document",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Recompute document",
        )
        if routed is not None:
            return routed
        return conn.server.recompute_document(doc_name)


def undo(conn, doc_name: str) -> dict[str, Any]:
        routed = conn._invoke_mutation_v2(
            "undo",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Undo",
        )
        if routed is not None:
            return routed
        return conn.server.undo(doc_name)


def redo(conn, doc_name: str) -> dict[str, Any]:
        routed = conn._invoke_mutation_v2(
            "redo",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Redo",
        )
        if routed is not None:
            return routed
        return conn.server.redo(doc_name)


def run_fem_analysis(
        conn, doc_name: str, analysis_name: str, timeout: int = 600
    ) -> dict[str, Any]:
        # The solver blocks the RPC response for up to `timeout` seconds, so the
        # socket must outlast it. The default 150 s transport timeout would abort
        # any solve longer than that even though the addon is still working.
        # Use a dedicated proxy whose socket timeout exceeds the solver timeout.
        rpc_timeout = max(conn._timeout, timeout + 30)
        routed = conn._invoke_mutation_v2(
            "run_fem_analysis",
            {
                "doc_name": doc_name,
                "analysis_name": analysis_name,
                "timeout": timeout,
            },
            document_names=(doc_name,),
            operation_name="Run FEM analysis",
            timeout=rpc_timeout,
        )
        if routed is not None:
            return routed
        proxy = conn._make_proxy(rpc_timeout)
        try:
            return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
        finally:
            if proxy is not conn.server:
                proxy.close()
