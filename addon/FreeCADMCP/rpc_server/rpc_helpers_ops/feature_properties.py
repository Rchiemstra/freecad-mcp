"""PartDesign feature property helpers."""

def _set_feature_bool(feature, property_names, value):
    """Set a boolean PartDesign property using version-compatible names."""
    properties = set(getattr(feature, "PropertiesList", []))
    for name in property_names:
        if name in properties:
            setattr(feature, name, bool(value))
            return name
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support any of: "
            + ", ".join(property_names)
        )
    return None


def _set_extrusion_symmetric(feature, value):
    """Set symmetric pad/pocket extrusion without touching deprecated Midplane."""
    properties = set(getattr(feature, "PropertiesList", []))
    if "SideType" in properties:
        candidates = ("Two sides", "Symmetric") if value else ("One side",)
        last_error = None
        for candidate in candidates:
            try:
                feature.SideType = candidate
                return "SideType"
            except Exception as err:
                last_error = err
        if last_error:
            raise last_error
    if "Symmetric" in properties:
        feature.Symmetric = bool(value)
        return "Symmetric"
    if "Midplane" in properties:
        if value:
            feature.Midplane = True
            return "Midplane"
        return None
    if value:
        raise AttributeError(
            f"{getattr(feature, 'TypeId', 'Feature')} does not support symmetric extrusion"
        )
    return None
