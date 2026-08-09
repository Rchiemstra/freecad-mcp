"""Property assignment from JSON-friendly dicts onto FreeCAD document objects."""

# §3.3 compatibility shims — moved symbols keep their legacy import path.
from .placement_codec import dict_to_placement
from .property_mapper_ops.object_dataclass import Object
from .property_mapper_ops.property_assignment import set_object_property
from .property_mapper_ops.reference_parsing import (
    parse_reference_entry,
    resolve_references,
)

__all__ = [
    "Object",
    "dict_to_placement",
    "parse_reference_entry",
    "resolve_references",
    "set_object_property",
]
