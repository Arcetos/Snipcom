from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

FAVORITES_TAG = "favorites"
FAVORITES_DEFAULT_COLOR = "#E8B44A"


def is_text_file(path: Path) -> bool:
    if not path.is_file():
        return False

    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type and mime_type.startswith("text/"):
        return True

    try:
        sample = path.read_bytes()[:4096]
    except OSError:
        return False

    return b"\x00" not in sample


def available_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        alternative = directory / f"{stem} ({counter}){suffix}"
        if not alternative.exists():
            return alternative
        counter += 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def split_tags(raw_tags: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for part in raw_tags.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        lowered = cleaned.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        tags.append(cleaned)
    return tags


def join_tags(tags: list[str]) -> str:
    return ", ".join(tags)


def has_tag(tags: list[str], target: str) -> bool:
    needle = target.strip().casefold()
    if not needle:
        return False
    return any(tag.strip().casefold() == needle for tag in tags if tag.strip())


def normalize_launch_options(launch_options: Mapping[str, object] | None) -> dict[str, object]:
    launch_options = launch_options or {}
    return {
        "keep_open": bool(launch_options.get("keep_open", True)),
        "ask_extra_arguments": bool(launch_options.get("ask_extra_arguments", False)),
        "copy_output_and_close": bool(launch_options.get("copy_output_and_close", False)),
        "use_linked_terminal": bool(launch_options.get("use_linked_terminal", True)),
    }


def slugify_casefold(text: str) -> str:
    lowered = text.strip().casefold()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-")


def natural_request_text(text: str) -> str:
    stripped = text.strip()
    if len(stripped) < 4:
        return ""
    prefix, separator, remainder = stripped.partition(" ")
    if prefix.casefold() != "nat" or not separator:
        return ""
    return remainder.strip()


def normalize_binding_sequences(
    raw_value: object,
    defaults: Mapping[str, list[str]],
    *,
    slot_count: int = 2,
) -> dict[str, list[str]]:
    loaded = raw_value if isinstance(raw_value, dict) else {}
    normalized: dict[str, list[str]] = {}
    safe_slot_count = max(1, int(slot_count))
    for action, default_sequences in defaults.items():
        value = loaded.get(action, default_sequences)
        sequences: list[str] = []
        if isinstance(value, list):
            sequences = [str(item).strip() for item in value[:safe_slot_count]]
        elif isinstance(value, str):
            sequences = [value.strip()]
        while len(sequences) < safe_slot_count:
            sequences.append("")
        normalized[action] = sequences[:safe_slot_count]
    return normalized


def read_json_file(path: Path, *, default: dict | None = None) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return default if default is not None else {}


def search_snippet(content: str, query: str) -> str:
    flattened = " ".join(content.split())
    if not flattened:
        return ""

    query_casefold = query.casefold()
    position = flattened.casefold().find(query_casefold)
    if position == -1:
        return flattened[:100]

    start = max(0, position - 30)
    end = min(len(flattened), position + len(query) + 70)
    snippet = flattened[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(flattened):
        snippet += "..."
    return snippet
