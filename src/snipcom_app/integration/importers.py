from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.helpers import join_tags, split_tags

# Regex to strip {{placeholder}} syntax used in tldr-pages commands.
_TLDR_PLACEHOLDER_RE = re.compile(r"\{\{([^}]*)\}\}")


@dataclass(frozen=True)
class ImportedCommand:
    title: str
    body: str
    snip_type: str
    family_key: str
    tags: tuple[str, ...]
    description: str
    source_kind: str
    source_ref: str
    source_license: str
    extra: dict[str, object]


@dataclass(frozen=True)
class ImportBatchPayload:
    label: str
    source_kind: str
    source_ref: str
    source_license: str
    commands: tuple[ImportedCommand, ...]

    @property
    def summary(self) -> dict[str, object]:
        families = sorted({command.family_key for command in self.commands if command.family_key}, key=str.casefold)
        return {
            "command_count": len(self.commands),
            "family_count": len(families),
            "families": families,
        }


def import_internal_json_pack(path: Path) -> ImportBatchPayload:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON pack root must be an object.")

    command_items = payload.get("commands", [])
    if not isinstance(command_items, list):
        raise ValueError("JSON pack must contain a commands list.")

    commands: list[ImportedCommand] = []
    for item in command_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", ""))
        if not title or not body.strip():
            continue
        snip_type = str(item.get("snip_type", "family_command")).strip()
        if snip_type != "family_command":
            snip_type = "family_command"
        family_key = str(item.get("family_key", "")).strip()
        if snip_type != "family_command":
            family_key = ""
        raw_tags = item.get("tags", [])
        if isinstance(raw_tags, list):
            tags = tuple(split_tags(join_tags([str(tag) for tag in raw_tags])))
        else:
            tags = tuple(split_tags(str(raw_tags or "")))
        commands.append(
            ImportedCommand(
                title=title,
                body=body,
                snip_type=snip_type,
                family_key=family_key,
                tags=tags,
                description=str(item.get("description", "")).strip(),
                source_kind=str(item.get("source_kind", "json-pack")).strip() or "json-pack",
                source_ref=str(item.get("source_ref", path.name)).strip(),
                source_license=str(item.get("source_license", "")).strip(),
                extra=item.get("extra") if isinstance(item.get("extra"), dict) else {},
            )
        )

    label = str(payload.get("label", path.stem)).strip() or path.stem
    return ImportBatchPayload(
        label=label,
        source_kind="json-pack",
        source_ref=str(path),
        source_license=str(payload.get("source_license", "")).strip(),
        commands=tuple(commands),
    )


def import_navi_cheats(source_path: Path, *, source_license: str = "") -> ImportBatchPayload:
    cheat_files = collect_files(source_path, ".cheat")
    commands: list[ImportedCommand] = []
    for cheat_file in cheat_files:
        commands.extend(parse_navi_cheat_file(cheat_file, source_root=source_path, source_license=source_license))
    label = source_path.stem or source_path.name or "Navi import"
    return ImportBatchPayload(
        label=label,
        source_kind="navi-cheat",
        source_ref=str(source_path),
        source_license=source_license,
        commands=tuple(commands),
    )


def import_cheatsheets(source_path: Path, *, source_license: str = "") -> ImportBatchPayload:
    candidates = collect_text_like_files(source_path)
    commands: list[ImportedCommand] = []
    for candidate in candidates:
        commands.extend(parse_cheatsheet_file(candidate, source_root=source_path, source_license=source_license))
    label = source_path.stem or source_path.name or "Cheatsheet import"
    return ImportBatchPayload(
        label=label,
        source_kind="cheatsheet",
        source_ref=str(source_path),
        source_license=source_license,
        commands=tuple(commands),
    )


def import_tldr_pages(source_path: Path, *, source_license: str = "CC0-1.0") -> ImportBatchPayload:
    """Import tldr-pages markdown files (# title / > desc / - example: / `cmd` format).

    When source_path is the root of a tldr-pages repository (contains pages/),
    only the English common + linux sections are imported to avoid 40x duplication
    from translated pages and OS-specific pages not relevant on Linux.
    """
    pages_root = source_path / "pages"
    if pages_root.is_dir():
        # Scoped import: English common + linux sections only (~6k pages total).
        md_files: list[Path] = []
        for section in ("common", "linux"):
            section_dir = pages_root / section
            if section_dir.is_dir():
                md_files.extend(sorted(section_dir.glob("*.md"), key=lambda p: p.name.casefold()))
    else:
        md_files = collect_files(source_path, ".md")

    commands: list[ImportedCommand] = []
    for md_file in md_files:
        commands.extend(parse_tldr_page_file(md_file, source_root=source_path, source_license=source_license))
    label = source_path.stem or source_path.name or "tldr-pages import"
    return ImportBatchPayload(
        label=label,
        source_kind="tldr-pages",
        source_ref=str(source_path),
        source_license=source_license,
        commands=tuple(commands),
    )


def parse_tldr_page_file(path: Path, *, source_root: Path, source_license: str) -> list[ImportedCommand]:
    """Parse a single tldr-pages markdown file into ImportedCommand entries.

    Format:
        # command-name
        > Description line(s).
        - Example description:
        `command --option {{placeholder}}`
    Each backtick-command block becomes one ImportedCommand.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    family_key = path.stem  # e.g. "tar", "git-commit"
    commands: list[ImportedCommand] = []
    pending_description = ""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("# "):
            family_key = stripped[2:].strip() or path.stem
            continue

        if stripped.startswith("> "):
            # Page-level description — not per-command, skip for entries
            continue

        if stripped.startswith("- ") and stripped.endswith(":"):
            pending_description = stripped[2:].rstrip(":").strip()
            continue

        if stripped.startswith("`") and stripped.endswith("`") and len(stripped) > 2:
            body = _TLDR_PLACEHOLDER_RE.sub(r"\1", stripped[1:-1].strip())
            if not body:
                continue
            commands.append(
                ImportedCommand(
                    title=body[:120],
                    body=body,
                    snip_type="family_command",
                    family_key=family_key,
                    tags=(family_key,) if family_key else (),
                    description=pending_description,
                    source_kind="tldr-pages",
                    source_ref=str(path.relative_to(source_root if source_root.is_dir() else path.parent)),
                    source_license=source_license,
                    extra={},
                )
            )
            pending_description = ""
            continue

    return commands


def export_internal_json_pack(path: Path, commands: list[dict[str, object]], *, label: str, source_license: str = "") -> None:
    payload = {
        "format": "snipcom-pack-v1",
        "label": label,
        "source_license": source_license,
        "commands": commands,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def collect_files(source_path: Path, suffix: str) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.casefold() == suffix.casefold() else []
    return sorted(
        [path for path in source_path.rglob(f"*{suffix}") if path.is_file()],
        key=lambda item: item.as_posix().casefold(),
    )


def collect_text_like_files(source_path: Path) -> list[Path]:
    if source_path.is_file():
        suffix = source_path.suffix.casefold()
        if suffix in {".txt", ".md", ".markdown", ".cheat"}:
            return [source_path]
        if not suffix and is_probable_cheatsheet_file(source_path):
            return [source_path]
        return []
    suffixes = {".txt", ".md", ".markdown", ".cheat"}
    ignored_names = {
        "readme",
        "readme.md",
        "license",
        "copying",
        "authors",
        "contributors",
        "changelog",
        "code_of_conduct",
        "contributing",
    }
    files: list[Path] = []
    for path in source_path.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(source_path).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        lowered_name = path.name.casefold()
        if lowered_name in ignored_names:
            continue
        suffix = path.suffix.casefold()
        if suffix in suffixes:
            files.append(path)
            continue
        if not suffix and is_probable_cheatsheet_file(path):
            files.append(path)
    return sorted(
        files,
        key=lambda item: item.as_posix().casefold(),
    )


def is_probable_cheatsheet_file(path: Path) -> bool:
    try:
        if path.stat().st_size > 262_144:
            return False
        raw = path.read_bytes()[:65_536]
    except OSError:
        return False
    if not raw or b"\x00" in raw:
        return False
    text = raw.decode("utf-8", errors="replace")
    non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not non_empty_lines:
        return False
    command_like = 0
    comment_like = 0
    for line in non_empty_lines[:220]:
        normalized = line.lstrip("-*").strip()
        if normalized.startswith("`") and normalized.endswith("`") and len(normalized) > 2:
            normalized = normalized.strip("`")
        if normalized.startswith("#"):
            comment_like += 1
        if looks_like_command_line(normalized):
            command_like += 1
    if command_like == 0:
        return False
    return comment_like > 0 or command_like >= 2


def parse_navi_cheat_file(path: Path, *, source_root: Path, source_license: str) -> list[ImportedCommand]:
    text = path.read_text(encoding="utf-8")
    commands: list[ImportedCommand] = []
    heading_family = path.stem
    heading_tags: list[str] = [heading_family] if heading_family else []
    provider_lines: list[str] = []
    comment_lines: list[str] = []
    command_lines: list[str] = []

    def flush_current() -> None:
        nonlocal comment_lines, command_lines, provider_lines
        body = "\n".join(line.rstrip() for line in command_lines).strip()
        if not body:
            comment_lines = []
            command_lines = []
            provider_lines = []
            return
        description = " ".join(line.strip() for line in comment_lines if line.strip()).strip()
        title = body.splitlines()[0].strip()
        commands.append(
            ImportedCommand(
                title=title[:120],
                body=body,
                snip_type="family_command",
                family_key=heading_family,
                tags=tuple(split_tags(join_tags(heading_tags))),
                description=description,
                source_kind="navi-cheat",
                source_ref=str(path.relative_to(source_root if source_root.is_dir() else path.parent)),
                source_license=source_license,
                extra={"providers": list(provider_lines)} if provider_lines else {},
            )
        )
        comment_lines = []
        command_lines = []
        provider_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("%"):
            flush_current()
            heading_text = stripped[1:].strip()
            heading_parts = [part.strip() for part in heading_text.split(",") if part.strip()]
            heading_family = heading_parts[0] if heading_parts else path.stem
            heading_tags = heading_parts or ([heading_family] if heading_family else [])
            continue
        if stripped.startswith("$"):
            provider_lines.append(stripped[1:].strip())
            continue
        if not stripped:
            flush_current()
            continue
        if stripped.startswith("#"):
            comment_lines.append(stripped[1:].lstrip())
            continue
        command_lines.append(line)

    flush_current()
    return commands


def parse_cheatsheet_file(path: Path, *, source_root: Path, source_license: str) -> list[ImportedCommand]:
    text = path.read_text(encoding="utf-8")
    front_matter, body_text = split_front_matter(text)
    front_tags = parse_simple_tags(front_matter.get("tags"))
    family_key = infer_family_key(path, source_root, front_tags)
    commands: list[ImportedCommand] = []
    comment_lines: list[str] = []
    command_lines: list[str] = []

    def flush_current() -> None:
        nonlocal comment_lines, command_lines
        body = "\n".join(line.rstrip() for line in command_lines).strip()
        if not body:
            comment_lines = []
            command_lines = []
            return
        description = " ".join(line.strip() for line in comment_lines if line.strip()).strip()
        title = body.splitlines()[0].strip()
        tags = list(front_tags)
        if family_key and family_key not in tags:
            tags.insert(0, family_key)
        commands.append(
            ImportedCommand(
                title=title[:120],
                body=body,
                snip_type="family_command",
                family_key=family_key,
                tags=tuple(split_tags(join_tags(tags))),
                description=description,
                source_kind="cheatsheet",
                source_ref=str(path.relative_to(source_root if source_root.is_dir() else path.parent)),
                source_license=source_license,
                extra={"front_matter": front_matter} if front_matter else {},
            )
        )
        comment_lines = []
        command_lines = []

    for raw_line in body_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_current()
            continue
        if stripped.startswith("#"):
            comment_lines.append(stripped[1:].lstrip())
            continue
        if looks_like_command_line(stripped):
            command_lines.append(stripped)
            continue
        if command_lines:
            command_lines.append(line)
            continue
        comment_lines.append(stripped)

    flush_current()
    return commands


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}, text
    closing_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing_index = index
            break
    if closing_index < 0:
        return {}, text
    front_matter = parse_simple_front_matter(lines[1:closing_index])
    body = "\n".join(lines[closing_index + 1 :])
    return front_matter, body


def parse_simple_front_matter(lines: list[str]) -> dict[str, object]:
    data: dict[str, object] = {}
    current_list_key = ""
    current_list: list[str] = []
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_list_key:
            current_list.append(stripped[2:].strip())
            data[current_list_key] = list(current_list)
            continue
        current_list_key = ""
        current_list = []
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            current_list_key = key
            current_list = []
            data[key] = current_list
            continue
        if value.startswith("[") and value.endswith("]"):
            parts = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
            data[key] = parts
            continue
        data[key] = value.strip("'\"")
    return data


def parse_simple_tags(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return split_tags(value)
    return []


def infer_family_key(path: Path, source_root: Path, front_tags: list[str]) -> str:
    if front_tags:
        return front_tags[0]
    if source_root.is_dir():
        relative_parts = path.relative_to(source_root).parts
        if len(relative_parts) > 1:
            return relative_parts[0].strip()
    return path.stem.strip()


# ---------------------------------------------------------------------------
# Command-line detection helpers used by the cheatsheet importer
# ---------------------------------------------------------------------------

# Common shell command prefixes — lines starting with any of these are treated
# as command bodies.  Keep alphabetically sorted within logical groups.
_CMD_LINE_PREFIXES: tuple[str, ...] = (
    "./", "/", "~",
    # privilege / environment
    "sudo ", "su ", "env ", "export ", "unset ", "source ", ". /", ". ~/",
    # version control
    "git ", "svn ", "hg ", "gh ",
    # package managers
    "apk ", "apt ", "apt-cache ", "apt-get ", "apt-key ", "apt-mark ",
    "brew ", "dnf ", "dpkg ", "flatpak ", "pacman ", "pip ", "pip3 ", "pipx ",
    "rpm ", "snap ", "yum ", "zypper ",
    # file / text
    "awk ", "cat ", "comm ", "cut ", "diff ", "find ", "grep ", "egrep ", "fgrep ",
    "head ", "join ", "less ", "locate ", "ls", "more ", "mv ", "paste ",
    "printf ", "rg ", "sed ", "sort ", "stat ", "tail ", "tee ", "tr ",
    "uniq ", "wc ", "which ", "type ",
    # file-system ops
    "chmod ", "chown ", "chgrp ", "cp ", "ln ", "mkdir ", "rmdir ", "rm ", "touch ",
    "umask ", "mount ", "umount ", "fdisk ", "lsblk ", "mkfs ",
    # archive / compress
    "7z ", "bzip2 ", "gzip ", "gunzip ", "tar ", "unzip ", "xz ", "zip ",
    # shell / scripting
    "bash ", "dash ", "echo ", "fish ", "ksh ", "read ", "sh ", "zsh ",
    "xargs ", "parallel ",
    # process / system
    "date ", "df ", "du ", "file ", "htop ", "id ", "journalctl ", "kill ",
    "killall ", "lsof ", "md5sum ", "netstat ", "nmap ", "pgrep ", "ping ",
    "pkill ", "ps ", "pwd", "sha1sum ", "sha256sum ", "ss ", "systemctl ",
    "top ", "traceroute ", "uptime ", "whoami ",
    # network
    "curl ", "dig ", "ftp ", "ip ", "ifconfig ", "nslookup ", "rsync ",
    "scp ", "sftp ", "ssh ", "wget ",
    # editors
    "emacs ", "nano ", "nvim ", "vim ",
    # terminal multiplexers
    "screen ", "tmux ",
    # containers / cloud
    "ansible ", "aws ", "az ", "docker ", "doctl ", "gcloud ", "helm ",
    "kubectl ", "packer ", "podman ", "terraform ", "vagrant ",
    # languages / build
    "cargo ", "cmake ", "deno ", "ffmpeg ", "gcc ", "g++ ", "clang ",
    "go ", "gradle ", "java ", "javac ", "make ", "mvn ", "ninja ",
    "node ", "npm ", "npx ", "openssl ", "gpg ", "pnpm ",
    "python ", "python3 ", "rustc ", "rustup ", "yarn ",
    # databases
    "mongosh ", "mysql ", "psql ", "redis-cli ", "sqlite3 ",
    # misc tools
    "convert ", "gpg ", "jq ", "magick ", "ssh-keygen ", "xdg-open ",
    "yq ", "strace ", "ltrace ",
    # user management
    "groupadd ", "passwd ", "useradd ", "userdel ", "usermod ",
)

# Shell operators that are strong evidence a line is a command regardless of prefix.
_SHELL_OPS: tuple[str, ...] = (
    " | ",    # pipeline with spaces (most common)
    "|",      # pipeline without spaces: cmd|cmd
    " && ",   # boolean AND
    " || ",   # boolean OR
    " > ",    " >> ",   # stdout redirect
    " 2> ",   " &> ",   # stderr / combined redirect
    " < ",    " << ",   # stdin / heredoc
    "`",      # command substitution (backtick)
    "$(",     # command substitution $()
    "${",     # variable expansion ${}
)


def looks_like_command_line(line: str) -> bool:
    """Return True if *line* looks like a shell command rather than prose text.

    Uses two signals:
    1. Known command-name prefix (explicit allow-list).
    2. Unambiguous shell operator in the line (pipe, redirect, subshell, etc.).

    The old fallback of "has a space and doesn't end with :" was removed because
    it matched ordinary English sentences and caused thousands of false imports.
    """
    if line.startswith(_CMD_LINE_PREFIXES):
        return True
    return any(op in line for op in _SHELL_OPS)
