"""FreeCADGui call adapters captured by the composition root."""

from __future__ import annotations


class PersonalViewApiUnavailableError(RuntimeError):
    """Raised when the running FreeCAD build lacks personal-view APIs."""

    code = "PERSONAL_VIEW_API_UNAVAILABLE"

    def __init__(self, api_name: str) -> None:
        self.api_name = api_name
        super().__init__(
            "FreeCAD must expose "
            f"FreeCADGui.{api_name} "
            "(rebuild/redeploy past collaboration personal-view support)"
        )


def _require_personal_view_api(gui_module, api_name: str) -> None:
    if not hasattr(gui_module, api_name):
        raise PersonalViewApiUnavailableError(api_name)


def store(gui_module, document_name, actor_id, context):
    _require_personal_view_api(gui_module, "storePersonalViewContext")
    return gui_module.storePersonalViewContext(document_name, actor_id, context)


def snapshot(gui_module, document_name, actor_id):
    _require_personal_view_api(gui_module, "getPersonalViewContext")
    return gui_module.getPersonalViewContext(document_name, actor_id)


def restore(gui_module, document_name, actor_id, prior):
    if prior is None:
        _require_personal_view_api(gui_module, "removePersonalViewContext")
        return gui_module.removePersonalViewContext(document_name, actor_id)
    _require_personal_view_api(gui_module, "storePersonalViewContext")
    gui_module.storePersonalViewContext(document_name, actor_id, prior)
    return None


def render(
    gui_module,
    document_name,
    actor_id,
    width=-1,
    height=-1,
    background="Current",
    samples=-1,
):
    _require_personal_view_api(gui_module, "renderPersonalViewContext")
    return gui_module.renderPersonalViewContext(
        document_name,
        actor_id,
        width,
        height,
        background,
        samples,
    )


__all__ = [
    "PersonalViewApiUnavailableError",
    "render",
    "restore",
    "snapshot",
    "store",
]
