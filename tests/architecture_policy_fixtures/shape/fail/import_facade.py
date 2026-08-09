"""A facade made only from public leaf imports still owns its combined surface."""

from capabilities.assembly.joints import add_joint as add_joint
from capabilities.assembly.joints import remove_joint as remove_joint
from capabilities.diagnostics.health import inspect_health as inspect_health
from capabilities.diagnostics.health import list_diagnostics as list_diagnostics
from capabilities.export.files import export_file as export_file
from capabilities.export.files import serialize_file as serialize_file
from capabilities.fem.materials import apply_material as apply_material
from capabilities.fem.materials import inspect_material as inspect_material
from capabilities.object.properties import get_property as get_property
from capabilities.object.properties import set_property as set_property
from capabilities.ui.dialogs import close_dialog as close_dialog
from capabilities.ui.dialogs import open_dialog as open_dialog
