from __future__ import annotations

import re
import shutil
from collections.abc import Iterable, Mapping

from .ai import DEFAULT_OLLAMA_ENDPOINT


def _detect_native_package_manager() -> str:
    """Return the primary package manager available on this system."""
    for pm in ("apt", "pacman", "zypper", "dnf", "apk", "yum"):
        if shutil.which(pm):
            return pm
    return "rpm"  # fallback: rpm is always present on RHEL/Fedora


_NATIVE_PACKAGE_MANAGER: str = _detect_native_package_manager()


def ai_enabled(settings: Mapping[str, object]) -> bool:
    return bool(settings.get("ai_enabled", False))


def ai_provider(settings: Mapping[str, object]) -> str:
    value = str(settings.get("ai_provider", "ollama")).strip().casefold()
    return value or "ollama"


def ai_endpoint(settings: Mapping[str, object]) -> str:
    value = str(settings.get("ai_endpoint", DEFAULT_OLLAMA_ENDPOINT)).strip()
    return value or DEFAULT_OLLAMA_ENDPOINT


def ai_model(settings: Mapping[str, object]) -> str:
    value = str(settings.get("ai_model", "qwen2.5:7b")).strip()
    return value or "qwen2.5:7b"


def ai_timeout_seconds(settings: Mapping[str, object]) -> int:
    try:
        value = int(settings.get("ai_timeout_seconds", 35))
    except (TypeError, ValueError):
        value = 35
    return max(5, min(value, 180))


def ai_anchor_terms(*values: str) -> list[str]:
    anchors: list[str] = []
    for value in values:
        anchors.extend(
            token
            for token in re.split(r"[^a-zA-Z0-9_.-]+", value.casefold())
            if len(token) >= 3
        )
    return list(dict.fromkeys(anchors))


def primary_tool_for_ai(
    catalog_entries: Iterable[object],
    last_terminal_input: str,
    user_request: str,
) -> str:
    entries = list(catalog_entries)
    stopwords = {
        "a", "an", "the", "to", "for", "of", "in", "on", "with", "from",
        "way", "show", "check", "current", "all", "list", "open", "inspect", "view",
    }
    synonym_map = {
        "github": "git", "repo": "git", "repository": "git", "branch": "git", "commit": "git",
        "commits": "git", "merge": "git", "rebase": "git", "push": "git", "pull": "git",
        "package": _NATIVE_PACKAGE_MANAGER, "packages": _NATIVE_PACKAGE_MANAGER, "installed": _NATIVE_PACKAGE_MANAGER, "service": "systemctl",
        "services": "systemctl", "journal": "journalctl", "logs": "journalctl",
    }
    known_families = {
        str(getattr(entry, "family_key", "") or "").casefold()
        for entry in entries
        if str(getattr(entry, "family_key", "") or "").strip()
    }
    known_commands = {
        token
        for entry in entries
        if bool(getattr(entry, "is_command", False))
        for token in re.split(r"[^a-zA-Z0-9_.-]+", str(getattr(entry, "display_name", "")).casefold())
        if token
    }
    for value in (user_request, last_terminal_input):
        lowered = value.strip()
        if not lowered:
            continue
        first_segment = re.split(r"[|;&]", lowered, maxsplit=1)[0].strip()
        tokens = [token for token in re.split(r"[^a-zA-Z0-9_.-]+", first_segment.casefold()) if token]
        for token in tokens:
            cleaned = synonym_map.get(token, token)
            if cleaned in {"sudo", "env", "time", "command", "builtin", "nohup"} or cleaned in stopwords:
                continue
            if cleaned in known_families or cleaned in known_commands:
                return cleaned
        for token in tokens:
            cleaned = synonym_map.get(token, token)
            if cleaned in {"sudo", "env", "time", "command", "builtin", "nohup"} or cleaned in stopwords:
                continue
            if cleaned:
                return cleaned
    return ""
