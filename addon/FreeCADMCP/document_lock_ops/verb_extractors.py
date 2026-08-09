from __future__ import annotations


def _params0_doc(params: tuple) -> str | None:
    return params[0] if params else None


def _options_document(params: tuple) -> str | None:
    if len(params) < 2:
        return None
    options = params[1] if len(params) > 1 else None
    if isinstance(options, dict):
        return options.get("document")
    return None


def _none_doc(_params: tuple) -> str | None:
    return None
