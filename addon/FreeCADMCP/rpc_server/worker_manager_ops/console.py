"""Best-effort FreeCAD console logging for worker lifecycle events."""


def console_message(text: str) -> None:
    try:
        import FreeCAD

        FreeCAD.Console.PrintMessage(text if text.endswith("\n") else text + "\n")
    except Exception:
        pass
