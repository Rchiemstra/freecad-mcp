"""Tool export binding helpers."""

create_document = None


def bind_tool_exports(exports: dict[str, object]) -> None:
    globals()["create_document"] = exports["create_document"]
