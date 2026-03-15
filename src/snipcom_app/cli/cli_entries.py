from __future__ import annotations

import json
import readline
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ..core.helpers import FAVORITES_TAG, has_tag, normalize_launch_options, split_tags
from ..core.repository import SnipcomEntry
from ..core.safety import evaluate_command_risk
from .cli_context import CliContext


def _entry_scope(ctx: CliContext, scope: str) -> list[SnipcomEntry]:
    if scope == "catalog":
        return ctx.repository.catalog_entries(include_active_commands=False)
    if scope == "workflow":
        return ctx.repository.active_entries(ctx.tags, ctx.snip_types)
    entries = ctx.repository.catalog_entries(include_active_commands=True)
    known_ids = {entry.entry_id for entry in entries}
    for entry in ctx.repository.active_entries(ctx.tags, ctx.snip_types):
        if entry.entry_id not in known_ids:
            entries.append(entry)
    return entries


def _entry_text(ctx: CliContext, entry: SnipcomEntry) -> str:
    if entry.body:  # covers json_command and cached command entries
        return entry.body
    if entry.is_command and entry.command_id is not None:
        return ctx.repository.command_store.get_command(entry.command_id).body
    if entry.path is None:
        return ""
    try:
        return ctx.repository.read_text(entry.path)
    except (OSError, UnicodeDecodeError):
        return ""


def _entry_launch_options(ctx: CliContext, entry: SnipcomEntry) -> dict[str, object]:
    if entry.is_command and entry.command_id is not None:
        return dict(ctx.repository.command_store.get_command(entry.command_id).launch_options)
    if entry.path is None:
        return normalize_launch_options(None)
    key = ctx.repository.storage_key(entry.path)
    return normalize_launch_options(ctx.launch_options.get(key))


def _search_score(query: str, entry: SnipcomEntry, body: str, usage_count: int) -> int:
    query_text = query.casefold()
    if not query_text:
        return usage_count
    title = entry.display_name.casefold()
    tags = entry.tag_text.casefold()
    family = entry.family_key.casefold()
    text = body.casefold()
    score = usage_count
    if title == query_text:
        score += 120
    elif title.startswith(query_text):
        score += 80
    elif query_text in title:
        score += 40
    if query_text in tags:
        score += 20
    if query_text in family:
        score += 20
    if query_text in text:
        score += 15
    if entry.dangerous:
        score -= 2
    return score


def _find_entries(ctx: CliContext, query: str, *, scope: str, limit: int) -> list[SnipcomEntry]:
    usage_counts = ctx.repository.command_store.usage_counts()
    entries = _entry_scope(ctx, scope)
    scored: list[tuple[int, SnipcomEntry]] = []
    query_text = query.strip().casefold()
    for entry in entries:
        body = _entry_text(ctx, entry)
        if query_text:
            haystacks = [
                entry.display_name.casefold(),
                entry.tag_text.casefold(),
                entry.family_key.casefold(),
                body.casefold(),
                entry.source_kind.casefold(),
            ]
            if not any(query_text in haystack for haystack in haystacks):
                continue
        score = _search_score(query, entry, body, usage_counts.get(entry.command_id or -1, 0))
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], item[1].display_name.casefold(), item[1].entry_id))
    return [entry for _score, entry in scored[: max(1, limit)]]


def _workflow_entries(ctx: CliContext) -> list[SnipcomEntry]:
    entries = [entry for entry in _entry_scope(ctx, "workflow") if not entry.is_folder]
    entries.sort(key=lambda entry: (entry.display_name.casefold(), entry.entry_id))
    return entries


def _query_matches_entry(ctx: CliContext, entry: SnipcomEntry, query_text: str) -> bool:
    cleaned_query = query_text.strip().casefold()
    if not cleaned_query:
        return True
    body = _entry_text(ctx, entry).casefold()
    return cleaned_query in " ".join(
        (
            entry.display_name.casefold(),
            entry.tag_text.casefold(),
            entry.family_key.casefold(),
            entry.source_kind.casefold(),
            body,
        )
    )


def _resolve_entry(ctx: CliContext, selector: str, *, scope: str = "all", last_selection_entry_id: str = "") -> SnipcomEntry:
    cleaned = selector.strip()
    if not cleaned:
        raise ValueError("Selector cannot be empty.")
    if cleaned == ".":
        cleaned = last_selection_entry_id
        if not cleaned:
            raise ValueError("No previous selection for this profile. Select a command first, then use '.'.")
    if cleaned.startswith("command:"):
        entry = ctx.repository.entry_from_id(cleaned, ctx.tags, ctx.snip_types, include_trashed=False)
        if entry is None:
            raise ValueError(f"No entry found for {cleaned}.")
        return entry
    if cleaned.isdigit():
        entry = ctx.repository.entry_from_id(f"command:{cleaned}", ctx.tags, ctx.snip_types, include_trashed=False)
        if entry is not None:
            return entry

    entries = _entry_scope(ctx, scope)
    exact = [entry for entry in entries if entry.display_name.casefold() == cleaned.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError(f"Selector is ambiguous: {cleaned} (matches {len(exact)} entries).")

    fuzzy = [entry for entry in entries if cleaned.casefold() in entry.display_name.casefold()]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if not fuzzy:
        raise ValueError(f"No entry matches: {cleaned}")
    names = ", ".join(entry.display_name for entry in fuzzy[:6])
    raise ValueError(f"Selector is ambiguous: {cleaned}. Candidates: {names}")


def _confirm_risk_cli(command: str, reasons: tuple[str, ...], *, yes_risk: bool) -> bool:
    if not reasons or yes_risk:
        return True
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("Refusing risky command without --yes-risk in non-interactive mode.", file=sys.stderr)
        for reason in reasons:
            print(f"- {reason}", file=sys.stderr)
        return False
    print("Risky command detected:", file=sys.stderr)
    for reason in reasons:
        print(f"- {reason}", file=sys.stderr)
    print(command, file=sys.stderr)
    answer = input("Type 'yes' to continue: ").strip().casefold()
    return answer == "yes"


def _print_workspace(ctx: CliContext, entries: list[SnipcomEntry]) -> int:
    """Print workspace entries as an aligned table: name | command | description.
    Name and command never wrap (truncated). Description wraps to fill remaining width.
    """
    import shutil
    import textwrap

    if not entries:
        return 0
    descriptions = ctx.repository.load_descriptions()
    rows: list[tuple[str, str, str]] = []
    for entry in entries:
        name = entry.display_name
        body = _entry_text(ctx, entry)
        command = " ".join(body.splitlines()).strip() if body else "-"
        if entry.is_command:
            description = entry.description.strip()
        else:
            storage_key = entry.entry_id.partition(":")[2]
            description = descriptions.get(storage_key, "").strip()
        rows.append((name, command, description or "-"))

    term_width = max(60, shutil.get_terminal_size((100, 24)).columns)
    GAP = 2

    # Fixed max widths for name and command; description gets the rest.
    name_w = min(max(len("Name"), max(len(r[0]) for r in rows)), 28)
    cmd_w  = min(max(len("Command"), max(len(r[1]) for r in rows)), 50)
    desc_w = max(12, term_width - name_w - cmd_w - GAP * 2)

    def _trim(text: str, width: int) -> str:
        return text if len(text) <= width else text[:width - 1] + "…"

    headers = ("Name", "Command", "Description")
    widths  = (name_w, cmd_w, desc_w)
    header_line = ("  ".join(h.ljust(w) for h, w in zip(headers, widths))).rstrip()
    sep_line    = "  ".join("-" * w for w in widths)
    print(header_line)
    print(sep_line)

    for name, command, description in rows:
        name_col = _trim(name, name_w).ljust(name_w)
        cmd_col  = _trim(command, cmd_w).ljust(cmd_w)
        desc_lines = textwrap.wrap(description, width=desc_w) or ["-"]
        # First line alongside name + command
        print(f"{name_col}  {cmd_col}  {desc_lines[0]}")
        # Continuation lines indented under the description column
        indent = " " * (name_w + GAP + cmd_w + GAP)
        for continuation in desc_lines[1:]:
            print(f"{indent}{continuation}")

    return 0


def _print_find(entries: list[SnipcomEntry], *, as_json: bool) -> int:
    if as_json:
        payload = [
            {
                "entry_id": entry.entry_id,
                "name": entry.display_name,
                "snip_type": entry.snip_type,
                "family": entry.family_key,
                "tags": entry.tag_text,
                "scope": "catalog" if entry.catalog_only else "workflow",
                "dangerous": entry.dangerous,
            }
            for entry in entries
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for entry in entries:
        scope = "catalog" if entry.catalog_only else "workflow"
        print(
            f"{entry.entry_id}\t{entry.display_name}\t{entry.snip_type}\t{scope}\t"
            f"{entry.family_key or '-'}\t{entry.tag_text or '-'}"
        )
    return 0


def _launcher_program() -> str:
    launcher = Path(str(sys.argv[0] if sys.argv else "")).name.strip().casefold()
    if launcher in {"scm", "snipcom"}:
        return launcher
    return "scm"


def _interactive_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _picker_prompt_label() -> str:
    return f"{_launcher_program()}> "


def _format_entry_preview(ctx: CliContext, entry: SnipcomEntry, *, max_lines: int) -> str:
    return _format_entry_preview_with_context(ctx, entry, max_lines=max_lines, source_label="", reason="")


def _format_entry_preview_with_context(
    ctx: CliContext,
    entry: SnipcomEntry,
    *,
    max_lines: int,
    source_label: str,
    reason: str,
) -> str:
    body = _entry_text(ctx, entry)
    body_lines = body.splitlines() or ([body] if body else [])
    safe_limit = max(1, int(max_lines))
    visible_lines = body_lines[:safe_limit]
    hidden_count = max(0, len(body_lines) - len(visible_lines))
    scope = "catalog" if entry.catalog_only else "workflow"
    cli_hint = _launcher_program()
    methods = [f"{cli_hint} -s {entry.entry_id}"]
    if body.strip():
        methods.append(f"{cli_hint} -r {entry.entry_id}")
        methods.append(f"{cli_hint} -x {entry.entry_id}")

    output: list[str] = [
        f"Name: {entry.display_name}",
        f"Entry: {entry.entry_id}",
        f"Type: {entry.snip_type}",
        f"Scope: {scope}",
        f"Family: {entry.family_key or '-'}",
        f"Tags: {entry.tag_text or '-'}",
        f"Dangerous: {'yes' if entry.dangerous else 'no'}",
    ]
    if source_label:
        output.append(f"Source: {source_label}")
    if reason:
        output.append(f"Reason: {reason}")
    launch_options = _entry_launch_options(ctx, entry)
    if not entry.is_folder:
        output.append(
            "Launch options: "
            f"keep_open={int(bool(launch_options.get('keep_open', True)))} "
            f"ask_extra_arguments={int(bool(launch_options.get('ask_extra_arguments', False)))} "
            f"copy_output_and_close={int(bool(launch_options.get('copy_output_and_close', False)))}"
        )
    output.append("")
    output.append("Methods:")
    output.extend(f"  {method}" for method in methods)
    output.append("")
    output.append("Body:")
    if not visible_lines:
        output.append("[empty]")
    else:
        output.extend(visible_lines)
        if hidden_count:
            output.append(f"... [{hidden_count} more line(s)]")
    return "\n".join(output)


def _fzf_preview_command(profile_slug: str, *, preview_lines: int) -> str:
    safe_lines = max(1, int(preview_lines))
    return " ".join(
        [
            shlex.quote(_launcher_program()),
            "-preview",
            "--entry-id",
            "{1}",
            "-P",
            shlex.quote(profile_slug),
            "--lines",
            str(safe_lines),
        ]
    )


def _select_numbered_entry(
    ctx: CliContext,
    entries: list[SnipcomEntry],
    *,
    preview: bool,
    preview_lines: int,
) -> SnipcomEntry | None:
    if not entries:
        return None
    while True:
        for index, entry in enumerate(entries, start=1):
            print(f"{index:2d}. {entry.display_name} [{entry.entry_id}]")
        choice = input("Select entry number (blank to cancel): ").strip()
        if not choice:
            return None
        try:
            selected_index = int(choice)
        except ValueError:
            print("Invalid number. Try again.", file=sys.stderr)
            continue
        if selected_index < 1 or selected_index > len(entries):
            print("Selection out of range. Try again.", file=sys.stderr)
            continue
        selected_entry = entries[selected_index - 1]
        if not preview:
            return selected_entry

        print("")
        print(_format_entry_preview(ctx, selected_entry, max_lines=preview_lines))
        print("")
        confirm = input("Use this entry? [Enter=yes, n=reselect, q=cancel]: ").strip().casefold()
        if confirm in {"", "y", "yes"}:
            return selected_entry
        if confirm in {"q", "quit", "c", "cancel"}:
            return None
        print("")


def _history_lines(shell_name: str, *, last: int) -> list[str]:
    shell = shell_name.strip().casefold()
    if shell == "zsh":
        path = Path.home() / ".zsh_history"
    else:
        path = Path.home() / ".bash_history"
    if not path.exists():
        raise FileNotFoundError(path)
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if shell == "zsh" and line.startswith(": "):
            line = line.split(";", 1)[1] if ";" in line else ""
            line = line.strip()
        if not line:
            continue
        lines.append(line)
    return lines[-max(1, last) :]


def _pick_entry(
    ctx: CliContext,
    query: str,
    *,
    scope: str,
    limit: int,
    preview: bool,
    preview_lines: int,
) -> SnipcomEntry | None:
    entries = _find_entries(ctx, query, scope=scope, limit=limit)
    if not entries:
        return None
    interactive = _interactive_tty()
    picker_lines = [
        f"{entry.entry_id}\t{entry.display_name}\t{entry.family_key or '-'}\t{entry.tag_text or '-'}"
        for entry in entries
    ]
    fzf = shutil.which("fzf")
    if fzf and interactive:
        fzf_args = [fzf, "--with-nth=2..", "--delimiter=\t", "--prompt", _picker_prompt_label()]
        if preview:
            fzf_args.extend(
                [
                    "--preview",
                    _fzf_preview_command(ctx.profile_slug, preview_lines=preview_lines),
                    "--preview-window",
                    "right:60%:wrap",
                ]
            )
        process = subprocess.run(
            fzf_args,
            input="\n".join(picker_lines),
            text=True,
            capture_output=True,
            check=False,
        )
        selected = process.stdout.strip()
        if not selected:
            return None
        selected_id = selected.split("\t", 1)[0].strip()
        return next((entry for entry in entries if entry.entry_id == selected_id), None)

    if not interactive:
        print("No interactive picker available. Install fzf or run in an interactive TTY.", file=sys.stderr)
        return None
    return _select_numbered_entry(ctx, entries, preview=preview, preview_lines=preview_lines)


def _pick_entry_numbered(
    ctx: CliContext,
    query: str,
    *,
    scope: str,
    limit: int,
    preview: bool,
    preview_lines: int,
) -> SnipcomEntry | None:
    entries = _find_entries(ctx, query, scope=scope, limit=limit)
    if not entries:
        return None
    if not _interactive_tty():
        print("Numbered picker requires an interactive TTY.", file=sys.stderr)
        return None
    return _select_numbered_entry(ctx, entries, preview=preview, preview_lines=preview_lines)


def _edit_command_text(initial: str) -> str:
    prompt = "Edit command and press Enter: "
    if not sys.stdin.isatty():
        return initial
    readline.set_startup_hook(lambda: readline.insert_text(initial))
    try:
        edited = input(prompt)
    finally:
        readline.set_startup_hook(None)
    cleaned = edited.strip()
    return cleaned or initial


def _record_cli_usage(ctx: CliContext, entry: SnipcomEntry, *, source: str) -> None:
    if entry.is_command and entry.command_id is not None:
        ctx.repository.command_store.record_usage(
            entry.command_id,
            event_kind="launch",
            terminal_label="cli",
            context={"source": source},
            track_transition=False,
        )


def _run_command_text(
    ctx: CliContext,
    entry: SnipcomEntry | None,
    command: str,
    *,
    yes_risk: bool,
    usage_source: str,
) -> int:
    cleaned = command.strip()
    if not cleaned:
        print("Selected entry is empty.", file=sys.stderr)
        return 2
    risk = evaluate_command_risk(cleaned, dangerous_flag=bool(entry.dangerous) if entry is not None else False)
    if not _confirm_risk_cli(cleaned, risk.reasons, yes_risk=yes_risk):
        return 3
    if entry is not None:
        _record_cli_usage(ctx, entry, source=usage_source)
    process = subprocess.run(["bash", "-lc", cleaned], check=False)
    return int(process.returncode)
