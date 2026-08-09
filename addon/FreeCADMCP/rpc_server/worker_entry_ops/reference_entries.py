"""Normalize FreeCAD link property values for worker validation."""


def reference_entries(value):
    """Normalize link values, excluding FreeCAD's whole-object ``""`` sentinel."""
    if hasattr(value, "Document") and hasattr(value, "Name"):
        return [(value, [])]
    if isinstance(value, tuple) and value and hasattr(value[0], "Document"):
        subs = []
        for item in value[1:]:
            if isinstance(item, str):
                if item:
                    subs.append(item)
            elif isinstance(item, (list, tuple)):
                subs.extend(str(sub) for sub in item if str(sub))
        return [(value[0], subs)]
    if isinstance(value, (list, tuple)):
        refs = []
        for item in value:
            refs.extend(reference_entries(item))
        return refs
    return []
