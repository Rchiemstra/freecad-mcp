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
        if value:
            try:
                feature.SideType = "Symmetric"
                return "SideType"
            except Exception:
                if "Midplane" in properties:
                    feature.Midplane = True
                    return "Midplane"
                raise
        feature.SideType = "One side"
        return "SideType"
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
