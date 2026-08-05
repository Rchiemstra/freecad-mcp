"""FreeCADGui call adapters captured by the composition root."""

from __future__ import annotations


def store(gui_module, document_name, actor_id, context):
    return gui_module.storePersonalViewContext(document_name, actor_id, context)


def snapshot(gui_module, document_name, actor_id):
    return gui_module.getPersonalViewContext(document_name, actor_id)


def restore(gui_module, document_name, actor_id, prior):
    if prior is None:
        return gui_module.removePersonalViewContext(document_name, actor_id)
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
    return gui_module.renderPersonalViewContext(
        document_name,
        actor_id,
        width,
        height,
        background,
        samples,
    )


__all__ = ["render", "restore", "snapshot", "store"]
