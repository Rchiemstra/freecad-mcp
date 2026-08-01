"""GUI adoption authorization helpers."""

def _confirm_dirty_document_adoption_gui(document, document_identity) -> bool:
    """Auto-authorize initial dirty adoption without opening a dialog.

    Starting an MCP agent implies write intent on an unlocked dirty document.
    """

    del document, document_identity
    return True


def _authorize_locked_error_handoff_gui(document, document_identity) -> bool:
    """Auto-authorize agent-start handoff without opening a dialog.

    The later GUI phase still revalidates the selected live document immediately
    before the atomic credential rotation.
    """

    del document, document_identity
    return True
