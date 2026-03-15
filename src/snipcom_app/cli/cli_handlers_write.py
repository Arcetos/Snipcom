from __future__ import annotations

import argparse
import subprocess
import sys

from .cli_context import CliContext, _context
from .cli_entries import _workflow_entries


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _read_multiline_input(prompt: str) -> str | None:
    """Read multiline input until Ctrl+D or two consecutive blank lines. Returns None on Ctrl+C."""
    print(prompt)
    print("  (enter two blank lines or press Ctrl+D to finish)")
    lines: list[str] = []
    blank_run = 0
    try:
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line == "":
                if blank_run >= 1:
                    if lines and lines[-1] == "":
                        lines.pop()
                    break
                blank_run += 1
                lines.append(line)
            else:
                blank_run = 0
                lines.append(line)
    except KeyboardInterrupt:
        print()
        return None
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _create_workflow_file(ctx: CliContext, name: str, contents: str, description: str) -> int:
    from ..core.helpers import available_path as _available_path
    file_name = name if name.endswith(".txt") else f"{name}.txt"
    path = _available_path(ctx.repository.texts_dir, file_name)
    try:
        path.write_text(contents, encoding="utf-8")
    except OSError as exc:
        print(f"Failed to create file: {exc}", file=sys.stderr)
        return 2
    if description:
        descs = ctx.repository.load_descriptions()
        descs[ctx.repository.storage_key(path)] = description
        ctx.repository.save_descriptions(descs)
    print(f"Created '{path.stem}' in workflow.")
    return 0


def _capture_terminal_output() -> str:
    """Return recent terminal output. Reads from stdin pipe or tmux pane."""
    if not sys.stdin.isatty():
        return sys.stdin.read()
    tmux_pane = __import__("os").environ.get("TMUX_PANE")
    if tmux_pane:
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", tmux_pane, "-S", "-500"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.rstrip().splitlines()
                return "\n".join(lines[:-1]).rstrip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return ""


def _copy_to_clipboard(text: str) -> bool:
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"]):
        try:
            proc = subprocess.run(cmd, input=text, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if proc.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


# ---------------------------------------------------------------------------
# Write handlers
# ---------------------------------------------------------------------------

def _create_user_command_interactive(ctx: CliContext) -> int:
    try:
        title = input("Title: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    if not title:
        print("Title is required.", file=sys.stderr)
        return 1
    body = _read_multiline_input("Body:")
    if body is None:
        return 1
    try:
        description = input("Description (optional, Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        description = ""
    ctx.repository.create_user_command(title, body, description)
    print(f"Created '{title}' as a command.")
    return 0


def _handle_new(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    print("Create:  1) Text file  2) Command")
    try:
        choice_str = input("Choice [1-2]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    if choice_str == "2":
        return _create_user_command_interactive(ctx)
    if choice_str != "1":
        print("Invalid choice.", file=sys.stderr)
        return 1
    try:
        name = input("File name: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    if not name:
        print("Name is required.", file=sys.stderr)
        return 1
    contents = _read_multiline_input("Contents:")
    if contents is None:
        return 1
    try:
        description = input("Description (optional, Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        description = ""
    return _create_workflow_file(ctx, name, contents, description)


def _handle_cto(args: argparse.Namespace) -> int:
    content = _capture_terminal_output()
    if not content:
        print(
            "Cannot capture terminal output from a regular terminal emulator —\n"
            "scrollback is not accessible to child processes.\n"
            "\n"
            "Options:\n"
            "  • Pipe output directly:  some-command | scm -cto\n"
            "  • Use the Linked Terminal (opened from the main app) — it runs\n"
            "    inside tmux, which makes capture possible.",
            file=sys.stderr,
        )
        return 1
    if _copy_to_clipboard(content):
        print(f"Copied {content.count(chr(10)) + 1} lines ({len(content)} chars) to clipboard.")
        return 0
    print("Could not access clipboard. Install wl-copy, xclip, or xsel.", file=sys.stderr)
    return 1


def _handle_sto(args: argparse.Namespace) -> int:
    content = _capture_terminal_output()
    if not content:
        print(
            "Cannot capture terminal output from a regular terminal emulator —\n"
            "scrollback is not accessible to child processes.\n"
            "\n"
            "Options:\n"
            "  • Pipe output directly:  some-command | scm -sto\n"
            "  • Use the Linked Terminal (opened from the main app) — it runs\n"
            "    inside tmux, which makes capture possible.",
            file=sys.stderr,
        )
        return 1
    ctx = _context(args.profile)
    print(f"Captured {content.count(chr(10)) + 1} lines ({len(content)} chars).\n")
    print("How to save?")
    print("  1. Prepend to top of existing file")
    print("  2. Append to bottom of existing file")
    print("  3. Replace contents of existing file")
    print("  4. Create new file with this content")
    print()
    try:
        choice_str = input("Choice [1-4]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    try:
        choice = int(choice_str)
    except ValueError:
        print("Invalid choice.", file=sys.stderr)
        return 1
    if choice not in (1, 2, 3, 4):
        print("Invalid choice.", file=sys.stderr)
        return 1
    if choice == 4:
        try:
            name = input("File name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if not name:
            print("Name is required.", file=sys.stderr)
            return 1
        try:
            description = input("Description (optional, Enter to skip): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            description = ""
        return _create_workflow_file(ctx, name, content, description)
    # Choices 1-3: pick an existing workflow file
    file_entries = [e for e in _workflow_entries(ctx) if e.is_file and e.path is not None]
    if not file_entries:
        print("No workflow text files found.", file=sys.stderr)
        return 1
    print()
    print("Select file:")
    for i, entry in enumerate(file_entries, 1):
        print(f"  {i:3}. {entry.display_name}")
    print()
    try:
        sel_str = input(f"File number [1-{len(file_entries)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    try:
        sel = int(sel_str)
    except ValueError:
        print("Invalid selection.", file=sys.stderr)
        return 1
    if sel < 1 or sel > len(file_entries):
        print("Invalid selection.", file=sys.stderr)
        return 1
    entry = file_entries[sel - 1]
    path = entry.path
    assert path is not None
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if choice == 1:
        new_content = content.rstrip("\n") + "\n" + existing
    elif choice == 2:
        new_content = existing.rstrip("\n") + ("\n" if existing else "") + content
    else:
        new_content = content
    try:
        path.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        print(f"Failed to write: {exc}", file=sys.stderr)
        return 2
    action = {1: "Prepended to", 2: "Appended to", 3: "Replaced"}[choice]
    print(f"{action} '{entry.display_name}'.")
    return 0


def _handle_add_from_history(args: argparse.Namespace) -> int:
    from .cli_entries import _history_lines
    ctx = _context(args.profile)
    try:
        lines = _history_lines(args.shell, last=args.last)
    except FileNotFoundError as exc:
        print(f"History file not found: {exc}", file=sys.stderr)
        return 2
    if not lines:
        print("No history commands found.", file=sys.stderr)
        return 2

    tags = [tag.strip() for tag in args.tags.split(",")] if args.tags else []
    created_ids: list[int] = []
    for index, line in enumerate(lines, start=1):
        title = args.title.strip() if args.title and len(lines) == 1 else line.splitlines()[0][:120]
        title = ctx.repository.unique_command_title(title)
        record = ctx.repository.command_store.create_command(
            title,
            body=line,
            snip_type="family_command",
            family_key=(args.family or "history").strip(),
            description="Imported from shell history",
            source_kind="shell-history",
            source_ref=args.shell,
            dangerous=bool(args.dangerous),
            tags=tags,
            extra={"history_index": index, "shell": args.shell},
        )
        created_ids.append(record.command_id)
    print(f"Added {len(created_ids)} command(s) from {args.shell} history.")
    return 0
