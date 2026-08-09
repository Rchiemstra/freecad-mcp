"""Configure allowed IPs workbench command."""

from PySide import QtWidgets

from ..ip_filter import validate_allowed_ips
from .dependencies import CommandDependencies, current_command_dependencies


class ConfigureAllowedIPsCommand:
    def __init__(self, dependencies: CommandDependencies | None = None) -> None:
        self._dependencies = dependencies or current_command_dependencies()

    def GetResources(self):
        return {
            "MenuText": "Configure Allowed IPs",
            "ToolTip": (
                "Set which IP addresses or subnets are allowed to connect "
                "to the RPC server."
            ),
        }

    def Activated(self):
        settings = self._dependencies.load_settings()
        current_ips = settings.get("allowed_ips", "127.0.0.1")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Allowed IP Addresses",
            "Enter allowed IP addresses or subnets (comma-separated):\n"
            "Examples: 127.0.0.1, 192.168.1.0/24, 10.0.0.5",
            QtWidgets.QLineEdit.Normal,
            current_ips,
        )
        if ok and text.strip():
            valid, errors = validate_allowed_ips(text.strip())
            if errors:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Invalid IP Configuration",
                    "The following errors were found:\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + ("\n\nOnly valid entries will be saved."
                       if valid else "\n\nNo valid entries found. Settings not changed."),
                )
            if not valid:
                self._dependencies.freecad.Console.PrintWarning(
                    "Allowed IPs not changed — no valid entries.\n"
                )
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            self._dependencies.save_settings(settings)
            self._dependencies.freecad.Console.PrintMessage(
                f"Allowed IPs updated to: {normalised}\n"
            )
            if self._dependencies.runtime_running():
                self._dependencies.freecad.Console.PrintMessage(
                    "Restart the RPC server for changes to take effect.\n"
                )
        else:
            self._dependencies.freecad.Console.PrintMessage(
                "Allowed IPs not changed.\n"
            )

    def IsActive(self):
        return True
