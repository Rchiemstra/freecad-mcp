"""JSON color arrays must satisfy FreeCAD's native tuple-only color setter."""

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.property_mapper_ops.property_assignment import (
    set_object_property,
)


class _NativeColorView:
    """Model the native PropertyColor conversion contract, not a permissive mock."""

    _colors = frozenset({"ShapeColor", "LineColor", "PointColor", "SelectionColor"})

    def getTypeIdOfProperty(self, name):
        return (
            "App::PropertyColor" if name in self._colors else "App::PropertyStringList"
        )

    def __setattr__(self, name, value):
        if name in self._colors and not (
            isinstance(value, tuple)
            and len(value) in (3, 4)
            and all(isinstance(channel, (int, float)) for channel in value)
        ):
            raise TypeError(
                "type must be integer or tuple of float or tuple integer, not list"
            )
        object.__setattr__(self, name, value)


@pytest.mark.parametrize("property_name", sorted(_NativeColorView._colors))
@pytest.mark.parametrize("channels", [[1, 0, 1], [0.1, 0.2, 0.3, 0.4]])
def test_nested_native_view_color_accepts_json_array(property_name, channels):
    view = _NativeColorView()
    obj = SimpleNamespace(PropertiesList=[], ViewObject=view)

    set_object_property(None, obj, {"ViewObject": {property_name: channels}})

    expected = tuple(float(channel) for channel in channels)
    if len(channels) == 3:
        expected += (1.0,)
    assert getattr(view, property_name) == expected
    assert all(type(channel) is float for channel in getattr(view, property_name))


@pytest.mark.parametrize("channels", [[1, 0, 1], [0.1, 0.2, 0.3, 0.4]])
def test_top_level_shape_color_remains_supported(channels):
    view = _NativeColorView()
    obj = SimpleNamespace(PropertiesList=[], ViewObject=view)

    set_object_property(None, obj, {"ShapeColor": channels})

    assert view.ShapeColor[:3] == tuple(channels[:3])


def test_non_color_view_properties_keep_their_native_input_types():
    view = _NativeColorView()
    obj = SimpleNamespace(PropertiesList=[], ViewObject=view)
    labels = ["one", "two"]

    set_object_property(
        None,
        obj,
        {
            "ViewObject": {
                "Visibility": False,
                "DisplayMode": "Shaded",
                "CustomLabels": labels,
            }
        },
    )

    assert view.Visibility is False
    assert view.DisplayMode == "Shaded"
    assert view.CustomLabels is labels


@pytest.mark.parametrize("property_name", ["LineColor", "PointColor"])
def test_malformed_view_color_is_rejected_before_native_assignment(property_name):
    view = _NativeColorView()
    obj = SimpleNamespace(PropertiesList=[], ViewObject=view)

    with pytest.raises(ValueError, match="RGB or RGBA"):
        set_object_property(None, obj, {"ViewObject": {property_name: [1, 0]}})

    assert not hasattr(view, property_name)
