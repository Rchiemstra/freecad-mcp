from __future__ import annotations

from ...responses.constants import ToolResponse
from ...template_resources import render_template_lines
from ..p7_assembly import _doc_preamble, _shared_helpers


def _response_text(resp: ToolResponse) -> str:
    return "".join(
        item.text for item in resp.content if getattr(item, "type", "") == "text"
    )

def _diag_preamble(doc_name: str) -> list[str]:
    return [
        *_doc_preamble(doc_name),
        *_shared_helpers(),
        *render_template_lines(
            "diagnostics/body_subpath_helpers.py.txt",
        ),
    ]
