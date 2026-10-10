"""Document postflight invariant validation."""

from __future__ import annotations

from typing import Any

_GENERIC_STATUS = frozenset({"", "error", "invalid", "touched", "valid", "freezed"})


def _status_text(reader: Any, argument: Any | None = None) -> str:
    if not callable(reader):
        return ""
    try:
        value = reader() if argument is None else reader(argument)
    except Exception:
        return ""
    return str(value or "").strip()


def _object_error_detail(obj: Any) -> str:
    """FreeCAD stores the recompute exception on the object status string."""

    texts = [_status_text(getattr(obj, "getStatusString", None))]
    document = getattr(obj, "Document", None)
    if document is None:
        getter = getattr(obj, "getDocument", None)
        document = getter() if callable(getter) else None
    texts.append(_status_text(getattr(document, "getErrorDescription", None), obj))
    for text in texts:
        if text.lower() not in _GENERIC_STATUS:
            return text
    return ""


def _invalid_object_label(obj: Any) -> str:
    name = str(getattr(obj, "Name", "<unnamed>"))
    detail = _object_error_detail(obj)
    if detail:
        return f"{name}: {detail}"
    return name


def validate_document_invariants(document: Any) -> dict[str, Any]:
    """Check recompute errors and basic PartDesign Body/Tip invariants."""

    errors: list[str] = []
    body_checks: list[dict[str, Any]] = []
    for obj in getattr(document, "Objects", ()):
        state = [str(item).lower() for item in getattr(obj, "State", ())]
        if any("error" in item or "invalid" in item for item in state):
            errors.append(_invalid_object_label(obj))
        try:
            is_body = obj.isDerivedFrom("PartDesign::Body")
        except Exception:
            is_body = getattr(obj, "TypeId", "") == "PartDesign::Body"
        if not is_body:
            continue
        group = tuple(getattr(obj, "Group", ()) or ())
        tip = getattr(obj, "Tip", None)
        tip_valid = tip is None or tip in group
        if not tip_valid:
            errors.append(f"{getattr(obj, 'Name', '<body>')}.Tip")
        body_checks.append(
            {
                "body": str(getattr(obj, "Name", "")),
                "member_count": len(group),
                "tip": getattr(tip, "Name", None),
                "tip_is_member": tip_valid,
            }
        )
    if errors:
        raise RuntimeError(
            "Document postflight validation failed: " + ", ".join(sorted(set(errors)))
        )
    return {"ok": True, "body_checks": body_checks}
