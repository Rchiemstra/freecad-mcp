from __future__ import annotations

from ...template_resources import render_template_lines


def _sk_preamble(doc_name: str, sketch_name: str) -> list[str]:
    return render_template_lines(
        "p1_curves/sk_preamble.py.txt",
        doc_name=repr(doc_name),
        sketch_name=repr(sketch_name),
    )
