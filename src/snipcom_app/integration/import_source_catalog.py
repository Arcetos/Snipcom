from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QColor


def default_import_sources_root() -> Path:
    return Path.home() / ".local" / "share" / "snipcom" / "import-sources"


IMPORT_SOURCES_ROOT = default_import_sources_root()

IMPORT_SOURCE_OPTIONS = {
    "navi-cheat": {
        "label": "Import Navi Cheats",
        "license": "CC0-1.0",
        "hint": "Select a local folder or .cheat file cloned from a Navi-style cheats repository.",
    },
    "cheatsheet": {
        "label": "Import Cheatsheets",
        "license": "CC0-1.0",
        "hint": "Select a local folder or file from a cheat/cheatsheets-style repository.",
    },
    "tldr-pages": {
        "label": "Import tldr-pages",
        "license": "CC0-1.0",
        "hint": "Select a local folder cloned from tldr-pages/tldr or compatible repository.",
    },
    "json-pack": {
        "label": "Import JSON Pack",
        "license": "",
        "hint": "Select a Snipcom JSON pack exported earlier.",
    },
}

LOCAL_PRESET_SOURCES = {
    "local-navi": {
        "label": "Import Local Navi Repo",
        "path": IMPORT_SOURCES_ROOT / "denisidoro-cheats",
        "license": "CC0-1.0",
        "source_kind": "navi-cheat",
    },
    "local-cheatsheets": {
        "label": "Import Local Cheatsheets Repo",
        "path": IMPORT_SOURCES_ROOT / "cheat-cheatsheets",
        "license": "CC0-1.0",
        "source_kind": "cheatsheet",
    },
}

RECOMMENDED_REPOSITORIES: tuple[dict[str, object], ...] = (
    {
        "key": "repo-navi-official",
        "name": "Navi Cheats (Official)",
        "source_kind": "navi-cheat",
        "url": "https://github.com/denisidoro/cheats.git",
        "license": "CC0-1.0",
        "estimated_commands": 600,
        "description": "Official navi cheat collection. ~600 practical shell workflows covering git, docker, kubernetes, networking, and more. High quality, all real commands.",
    },
    {
        "key": "repo-papanito-cheats",
        "name": "Papanito Cheats",
        "source_kind": "navi-cheat",
        "url": "https://github.com/papanito/cheats.git",
        "license": "",
        "estimated_commands": 500,
        "description": "Community navi cheat set with sysadmin and developer-focused commands.",
    },
    {
        "key": "repo-infosecstreams-cheats",
        "name": "Infosecstreams Cheat Sheets",
        "source_kind": "navi-cheat",
        "url": "https://github.com/infosecstreams/cheat.sheets.git",
        "license": "",
        "estimated_commands": 60,
        "description": "Security-focused navi cheat sheets covering recon, exploitation, and post-exploitation tools.",
    },
    {
        "key": "repo-fullbyte-navi",
        "name": "FullByte Navi Cheatsheet",
        "source_kind": "navi-cheat",
        "url": "https://github.com/FullByte/navi-cheatsheet.git",
        "license": "",
        "estimated_commands": 250,
        "description": "Community collection of practical one-liners and sysadmin/developer commands in navi .cheat format.",
    },
    {
        "key": "repo-cheatsheets-official",
        "name": "Cheat Cheatsheets",
        "source_kind": "cheatsheet",
        "url": "https://github.com/cheat/cheatsheets.git",
        "license": "CC0-1.0",
        "estimated_commands": 1500,
        "description": "Popular cheat-compatible command sheets covering ~150 tools. Extensionless files with '# description / command' format.",
    },
)


def repository_size_badge(estimated_commands: int) -> str:
    if estimated_commands >= 5000:
        return "HUGE"
    if estimated_commands >= 300:
        return "MEDIUM"
    return "SMALL"


def repository_badge_color(badge: str) -> QColor:
    normalized = badge.strip().upper()
    if normalized == "HUGE":
        return QColor("#C53030")
    if normalized == "MEDIUM":
        return QColor("#B7791F")
    return QColor("#2F855A")
