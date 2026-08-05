"""Remote connections toggle workbench command."""

from ..settings import LEASE_MODE_ENFORCE, is_loopback_host
from .dependencies import CommandDependencies, current_command_dependencies


class ToggleRemoteConnectionsCommand:
    def __init__(self, dependencies: CommandDependencies | None = None) -> None:
        self._dependencies = dependencies or current_command_dependencies()

    def GetResources(self):
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = self._dependencies.load_settings()
        requested = bool(checked)
        if (
            requested
            and settings.get("document_lease_mode") == LEASE_MODE_ENFORCE
            and not settings.get(
                "allow_authenticated_remote_without_transport_security", False
            )
        ):
            self._dependencies.freecad.Console.PrintWarning(
                "Remote Connections was not enabled: enforce mode keeps the addon "
                "on loopback because HMAC does not encrypt JSON-RPC. Use an SSH/TLS "
                "tunnel, or deliberately configure the unsafe transport override.\n"
            )
            return

        settings["remote_enabled"] = requested
        if requested and is_loopback_host(settings.get("rpc_bind_host")):
            # Preserve the pre-rpc_bind_host behavior for off/observe profiles:
            # the explicit remote toggle means listen on all IPv4 interfaces.
            settings["rpc_bind_host"] = "0.0.0.0"
        self._dependencies.save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            self._dependencies.freecad.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            self._dependencies.freecad.Console.PrintMessage(
                "Remote connections disabled.\n"
            )

        if self._dependencies.runtime_running():
            self._dependencies.freecad.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True
