"""Link policy validation and warn-mode filtering."""

from __future__ import annotations

from typing import Any


def apply_link_policy(
    links: list[dict[str, Any]],
    broken: list[str],
    invalid_subelements: list[str],
    *,
    link_policy: str,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]] | dict[str, Any]:
    """Return filtered links and warnings, or an error dict on strict failure."""
    if not broken and not invalid_subelements:
        return links, [], []

    if link_policy == "strict":
        if broken:
            return {
                "ok": False,
                "error_code": "external_link_unresolved",
                "error": "Broken or unopened links: " + ", ".join(broken),
            }
        return {
            "ok": False,
            "error_code": "external_subelement_unresolved",
            "error": "Nonexistent linked subelements: " + ", ".join(invalid_subelements),
        }

    link_warnings: list[str] = []
    for item in broken:
        link_warnings.append(f"broken_link:{item}")
    for item in invalid_subelements:
        link_warnings.append(f"invalid_subelement:{item}")

    invalid_set = set(invalid_subelements)
    ignored_links: list[dict[str, Any]] = []
    filtered_links = []
    for link in links:
        subs = [str(sub) for sub in link.get("subelements") or []]
        kept = [
            sub
            for sub in subs
            if f"{link['target_document']}.{link['target_object']}.{sub}"
            not in invalid_set
        ]
        ignored_subs = [sub for sub in subs if sub not in kept]
        if ignored_subs:
            ignored_links.append({
                "owner_document": link["owner_document"],
                "owner_object": link["owner_object"],
                "property": link["property"],
                "reference_index": int(link["reference_index"]),
                "target_document": link["target_document"],
                "target_object": link["target_object"],
                "subelements": ignored_subs,
            })
        if subs and not kept:
            continue
        entry = dict(link)
        entry["subelements"] = kept
        filtered_links.append(entry)
    return filtered_links, link_warnings, ignored_links
