"""Portable engineering labels. Display text never becomes a file name or DXF text."""
from __future__ import annotations

import hashlib
import re


class IdentityError(ValueError):
    pass


_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def component_identity(component: dict) -> dict:
    raw_id = component.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise IdentityError("component id must be a nonempty string")
    label = component.get("display_label", raw_id)
    if not isinstance(label, str):
        raise IdentityError("display_label must be a string")
    # No transliteration or lossy replacement. The raw UTF-8 ID has a stable hash.
    portable = bool(_SAFE.fullmatch(raw_id)) and raw_id.upper() not in _RESERVED
    machine_id = raw_id if portable else "C-" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:24]
    return {"component_id": raw_id, "machine_id": machine_id, "display_label": label,
            "raw_id": raw_id, "encoding": "UTF-8", "dxf_label_policy": "ASCII machine_id only"}


def identity_map(components: list[dict]) -> list[dict]:
    result, seen_ids, seen_files = [], set(), {}
    for component in components:
        entry = component_identity(component)
        raw, machine = entry["raw_id"], entry["machine_id"]
        if raw in seen_ids:
            raise IdentityError(f"duplicate component id: {raw!r}")
        # Windows file systems commonly compare names case-insensitively.
        key = machine.casefold()
        if key in seen_files:
            raise IdentityError(f"portable filename collision: {raw!r} and {seen_files[key]!r}; assign distinct stable IDs")
        seen_ids.add(raw)
        seen_files[key] = raw
        result.append(entry)
    return result
