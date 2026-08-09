"""Merge worker and snapshot link warnings without duplicates."""

from __future__ import annotations

from typing import Any


def merge_link_warnings(
    snapshot: dict[str, Any],
    worker_result: dict[str, Any],
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in (snapshot.get("link_warnings"), worker_result.get("link_warnings")):
        for item in source or []:
            text = str(item)
            if text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return merged


def apply_link_warnings(payload: dict[str, Any], link_warnings: list[str]) -> None:
    if not link_warnings:
        return
    payload["link_warnings"] = link_warnings
    structured = payload.get("structured")
    if isinstance(structured, dict):
        payload["structured"] = {**structured, "link_warnings": link_warnings}
    session = payload.get("session")
    if isinstance(session, dict):
        payload["session"] = {**session, "link_warnings": link_warnings}
