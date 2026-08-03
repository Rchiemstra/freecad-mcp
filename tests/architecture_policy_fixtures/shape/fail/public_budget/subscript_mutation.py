"""A slice mutation makes an otherwise explicit public surface unauditable."""

Visible = object()

__all__ = ["Visible"]


def dynamic_names():
    return ["Hidden"]


__all__[:] = dynamic_names()
