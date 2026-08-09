"""A module-level named expression makes __all__ unauditable."""

Visible = object()


def make_exports():
    return ["Visible"]


exports = (__all__ := make_exports())
