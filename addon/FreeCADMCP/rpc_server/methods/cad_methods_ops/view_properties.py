"""Apply ShapeColor and ViewObject after the App commit, on the GUI thread.

The document commit runs on the owner thread. ``ViewObject`` is a GUI API, so
those keys must not be assigned inside the mutation. ``on_gui`` is the same
executor restore uses (``_dispatch_snapshot_gui``): it runs the callable on the
Qt main thread. A string return is a dispatch error.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .typed_rpc_document import get_object

try:
    from ...property_mapper_ops.property_assignment import assign_view_property
except ImportError:  # pragma: no cover - flat addon import path
    from property_mapper_ops.property_assignment import assign_view_property

GuiExecutor = Callable[[Callable[[], object]], object]
PropertySetter = Callable[[object, object, dict[str, object]], object]

VIEW_PROPERTY_NAMES = frozenset({"ShapeColor", "ViewObject"})


def split_view_properties(
    properties: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Separate GUI presentation keys from properties that belong in the commit."""

    app_properties: dict[str, object] = {}
    view_properties: dict[str, object] = {}
    for key, value in properties.items():
        if key in VIEW_PROPERTY_NAMES:
            view_properties[key] = value
        else:
            app_properties[key] = value
    return app_properties, view_properties


def apply_view_properties_after_commit(
    document: object,
    object_name: str,
    view_properties: Mapping[str, object],
    set_object_property: PropertySetter | None,
    on_gui: GuiExecutor | None,
) -> str | None:
    """Assign view properties. Return an error string, or None on success.

    App properties are already committed. A failure here must not pretend the
    view step succeeded, and it must not roll those App properties back.
    """

    if not view_properties:
        return None
    payload = dict(view_properties)

    def assign() -> None:
        obj = get_object(document, object_name)
        if obj is None:
            raise RuntimeError(f"object {object_name!r} is missing after commit")
        if set_object_property is not None:
            set_object_property(document, obj, payload)
            return
        for key, value in payload.items():
            if not assign_view_property(obj, key, value):
                raise ValueError(f"Unsupported view property {key!r}")

    try:
        if on_gui is None:
            assign()
            result: object = None
        else:
            result = on_gui(assign)
    except Exception as exc:
        detail = str(exc) or type(exc).__name__
        return f"View properties were not applied on {object_name!r}: {detail}"
    if isinstance(result, str):
        return f"View properties were not applied on {object_name!r}: {result}"
    return None
