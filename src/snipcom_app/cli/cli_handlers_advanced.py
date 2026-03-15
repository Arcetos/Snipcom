from __future__ import annotations

import argparse
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from .cli_context import CliContext, APP_SUPPORT_DIR, _context, _last_selection_entry_id, _set_last_selection
from .cli_entries import (
    _confirm_risk_cli,
    _edit_command_text,
    _entry_text,
    _find_entries,
    _format_entry_preview_with_context,
    _interactive_tty,
    _pick_entry,
)
from .cli_nav import _generate_cli_ai_candidate
from .cli_shell import _shell_install, _shell_script
from ..ai.ai_shared import ai_enabled as _ai_enabled_setting
from ..core.safety import evaluate_command_risk
from ..integration.linked_terminal import (
    create_linked_terminal_session,
    dispatch_linked_terminal_command,
    launch_linked_terminal_session,
    linked_terminal_root_dir,
    list_linked_terminal_sessions,
)
from ..integration.source_sync import source_payload, sync_import_source, upsert_import_payload


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _source_targets(ctx: CliContext, target: str) -> list[int]:
    cleaned = target.strip()
    if cleaned.casefold() == "all":
        return [source.source_id for source in ctx.repository.list_import_sources()]
    if cleaned.isdigit():
        return [int(cleaned)]
    source = ctx.repository.get_import_source_by_name(cleaned)
    return [source.source_id]


# ---------------------------------------------------------------------------
# Advanced handlers
# ---------------------------------------------------------------------------

def _handle_send(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    try:
        from .cli_entries import _resolve_entry
        entry = _resolve_entry(ctx, args.selector, last_selection_entry_id=_last_selection_entry_id(ctx.profile_slug))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _set_last_selection(ctx.profile_slug, entry.entry_id, entry.display_name)
    command = _entry_text(ctx, entry).strip()
    if not command:
        print("Selected entry is empty.", file=sys.stderr)
        return 2

    risk = evaluate_command_risk(command, dangerous_flag=bool(entry.dangerous))
    if not _confirm_risk_cli(command, risk.reasons, yes_risk=args.yes_risk):
        return 3

    sessions = list_linked_terminal_sessions(linked_terminal_root_dir())
    session: dict[str, object] | None = None
    if args.session:
        for candidate in sessions:
            if str(candidate.get("label", "")).casefold() == args.session.casefold():
                session = candidate
                break
        if session is None:
            print(f"No linked terminal session named: {args.session}", file=sys.stderr)
            return 2
    elif sessions:
        session = sessions[0]

    if session is None:
        session = create_linked_terminal_session(linked_terminal_root_dir())
        runtime_dir = Path(session["runtime_dir"])
        label = str(session["label"])
        if not launch_linked_terminal_session(ctx.settings, runtime_dir, label, chooser=lambda: None):
            print(f"Could not launch {label}.", file=sys.stderr)
            return 4

    runtime_dir = Path(session["runtime_dir"])
    label = str(session["label"])
    delivery = dispatch_linked_terminal_command(runtime_dir, command)
    if entry.is_command and entry.command_id is not None:
        ctx.repository.command_store.record_usage(
            entry.command_id,
            event_kind="send",
            terminal_label=label,
            context={"runtime_dir": str(runtime_dir), "source": "cli-send"},
            track_transition=True,
        )
    print(f"{delivery}: {entry.display_name} -> {label}")
    return 0


def _handle_pick(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()
    entry = _pick_entry(
        ctx,
        query,
        scope=args.scope,
        limit=args.limit,
        preview=not bool(args.no_preview),
        preview_lines=max(1, int(args.preview_lines)),
    )
    if entry is None:
        return 1
    _set_last_selection(ctx.profile_slug, entry.entry_id, entry.display_name)
    command = _entry_text(ctx, entry).strip()
    if not command:
        return 1
    print(command)
    return 0


def _handle_nat(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()

    # Run AI generation in background while DB results are fetched.
    ai_name: str = ""
    ai_body: str = ""
    ai_done = threading.Event()

    def _ai_worker() -> None:
        nonlocal ai_name, ai_body
        candidate, _err = _generate_cli_ai_candidate(ctx, query)
        if candidate is not None:
            ai_name = candidate.entry.display_name
            ai_body = candidate.body
        ai_done.set()

    ai_thread: threading.Thread | None = None
    if query.strip() and _ai_enabled_setting(ctx.settings):
        ai_thread = threading.Thread(target=_ai_worker, daemon=True)
        ai_thread.start()

    entries = _find_entries(ctx, query, scope=args.scope, limit=args.limit)

    if not entries and ai_thread is None:
        print(f"No results for: {query!r}", file=sys.stderr)
        return 1

    if not _interactive_tty():
        print("Numbered picker requires an interactive TTY.", file=sys.stderr)
        return 1

    # Wait for AI with a capped timeout so UX stays responsive.
    if ai_thread is not None:
        sys.stderr.write("(AI generating...)\r")
        sys.stderr.flush()
        ai_done.wait(timeout=12)
        sys.stderr.write("                   \r")
        sys.stderr.flush()

    preview_lines = max(1, int(args.preview_lines))

    while True:
        for idx, entry in enumerate(entries, start=1):
            family = entry.family_key or entry.snip_type
            print(f"{idx:2d}. [{family}] {entry.display_name}")
        ai_index: int | None = None
        if ai_name:
            ai_index = len(entries) + 1
            print(f"{ai_index:2d}. [AI] {ai_name}")

        choice = input("Select number (blank=cancel): ").strip()
        if not choice:
            return 1
        try:
            n = int(choice)
        except ValueError:
            print("Invalid number.", file=sys.stderr)
            print("")
            continue

        if ai_index is not None and n == ai_index:
            body = ai_body or ai_name
            if not bool(args.no_preview):
                print(f"\nBody: {body}\n")
            confirm = input("Use this entry? [Enter=yes, n=reselect, q=cancel]: ").strip().casefold()
            if confirm in {"", "y", "yes"}:
                print(_edit_command_text(body))
                return 0
            if confirm in {"q", "quit", "c", "cancel"}:
                return 1
            print("")
            continue

        if n < 1 or n > len(entries):
            print("Out of range.", file=sys.stderr)
            print("")
            continue

        entry = entries[n - 1]
        body = _entry_text(ctx, entry).strip()
        if not body:
            print("Entry has no body.", file=sys.stderr)
            return 1
        if not bool(args.no_preview):
            print(f"\n{_format_entry_preview_with_context(ctx, entry, max_lines=preview_lines, source_label='', reason='')}\n")
        confirm = input("Use this entry? [Enter=yes, n=reselect, q=cancel]: ").strip().casefold()
        if confirm in {"", "y", "yes"}:
            _set_last_selection(ctx.profile_slug, entry.entry_id, entry.display_name)
            print(_edit_command_text(body))
            return 0
        if confirm in {"q", "quit", "c", "cancel"}:
            return 1
        print("")


def _handle_shell_print(args: argparse.Namespace) -> int:
    print(_shell_script(args.shell))
    return 0


def _handle_shell_install(args: argparse.Namespace) -> int:
    return _shell_install(args.shell)


def _handle_source_add(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    source_value = (args.git or args.path or "").strip()
    if not source_value:
        print("Either --path or --git is required.", file=sys.stderr)
        return 2
    is_git = bool(args.git)
    source_name = (args.name or Path(source_value).name or "source").strip()
    source = ctx.repository.upsert_import_source(
        name=source_name,
        kind=args.kind,
        path_or_url=source_value,
        is_git=is_git,
    )
    print(f"{source.source_id}\t{source.name}\t{source.kind}\t{source.path_or_url}\tgit={int(source.is_git)}")
    return 0


def _handle_source_list(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    sources = ctx.repository.list_import_sources()
    if args.json:
        payload = [
            {
                "id": source.source_id,
                "name": source.name,
                "kind": source.kind,
                "path_or_url": source.path_or_url,
                "is_git": source.is_git,
                "local_checkout_path": source.local_checkout_path,
                "last_sync_at": source.last_sync_at,
                "last_status": source.last_status,
                "last_batch_id": source.last_batch_id,
            }
            for source in sources
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    for source in sources:
        print(
            f"{source.source_id}\t{source.name}\t{source.kind}\t{source.path_or_url}\t"
            f"git={int(source.is_git)}\tlast={source.last_sync_at or '-'}\tstatus={source.last_status or '-'}"
        )
    return 0


def _handle_source_refresh(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    try:
        source_ids = _source_targets(ctx, args.target)
    except KeyError:
        print(f"Unknown source: {args.target}", file=sys.stderr)
        return 2
    if not source_ids:
        print("No import sources configured.", file=sys.stderr)
        return 2

    failures = 0
    for source_id in source_ids:
        try:
            result = sync_import_source(ctx.repository, source_id=source_id, app_support_dir=APP_SUPPORT_DIR)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            try:
                ctx.repository.update_import_source(
                    source_id,
                    last_sync_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    last_status=f"error: {exc}",
                )
            except (KeyError, OSError, ValueError):
                pass
            print(f"[error] source {source_id}: {exc}", file=sys.stderr)
            continue
        print(
            f"[ok] {result['name']}: created={result['created']} updated={result['updated']} "
            f"skipped={result['skipped']} batch={result['batch_id']}"
        )
    return 1 if failures else 0


def _handle_source_import_once(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    payload = source_payload(args.kind, Path(args.path).expanduser())
    result = upsert_import_payload(
        ctx.repository,
        payload,
        source_ref_override=str(Path(args.path).expanduser()),
        label_override=args.label or payload.label,
    )
    print(
        f"Imported batch={result['batch_id']} created={result['created']} "
        f"updated={result['updated']} skipped={result['skipped']}"
    )
    return 0
