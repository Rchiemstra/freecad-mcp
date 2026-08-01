"""Remote connections toggle workbench command."""

from ..settings import LEASE_MODE_ENFORCE, is_loopback_host


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        from .. import commands, rpc_server
        settings = commands.load_settings()
        requested = bool(checked)
        if (
            requested
            and settings.get("document_lease_mode") == LEASE_MODE_ENFORCE
            and not settings.get(
                "allow_authenticated_remote_without_transport_security", False
            )
        ):
            commands.FreeCAD.Console.PrintWarning(
                "Remote Connections was not enabled: enforce mode keeps the addon "
                "on loopback because HMAC does not encrypt XML-RPC. Use an SSH/TLS "
                "tunnel, or deliberately configure the unsafe transport override.\n"
            )
            return

        settings["remote_enabled"] = requested
        if requested and is_loopback_host(settings.get("rpc_bind_host")):
            # Preserve the pre-rpc_bind_host behavior for off/observe profiles:
            # the explicit remote toggle means listen on all IPv4 interfaces.
            settings["rpc_bind_host"] = "0.0.0.0"
        commands.save_settings(settings)

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            commands.FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            commands.FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server.rpc_server_instance:
            commands.FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True
