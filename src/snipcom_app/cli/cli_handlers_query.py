from __future__ import annotations

import argparse
import json
import sys

from .cli_context import _context, _last_selection_entry_id, _set_last_selection
from .cli_entries import (
    _edit_command_text,
    _entry_text,
    _find_entries,
    _format_entry_preview_with_context,
    _interactive_tty,
    _print_find,
    _print_workspace,
    _query_matches_entry,
    _resolve_entry,
    _run_command_text,
    _workflow_entries,
)
from .cli_handlers_write import _create_workflow_file
from .cli_nav import _nav_candidates, _nav_outcome, _select_numbered_nav_candidate
from ..core.helpers import FAVORITES_TAG, has_tag, split_tags
from ..core.repository import SnipcomEntry


# ---------------------------------------------------------------------------
# Private helpers (only used by _handle_nav in this module)
# ---------------------------------------------------------------------------

def _emit_nav_selection(command: str) -> int:
    cleaned = command.rstrip("\n")
    if not cleaned:
        return 1
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    print(" && ".join(lines) if lines else cleaned)
    return 0


def _should_persist_last_selection(entry: SnipcomEntry | None) -> bool:
    return entry is not None and not entry.entry_id.startswith("synthetic:")


# ---------------------------------------------------------------------------
# Query handlers
# ---------------------------------------------------------------------------

def _handle_find(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()
    entries = _find_entries(ctx, query, scope=args.scope, limit=args.limit)
    return _print_find(entries, as_json=args.json)


def _handle_nav(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()
    mode = "execute" if sys.stdout.isatty() else "return"
    used_sectioned_ui, outcome = _nav_outcome(
        ctx,
        query,
        limit=max(1, int(args.limit)),
        include_context=not bool(args.no_context),
        include_database=not bool(args.no_database),
        mode=mode,
    )
    if outcome is None and not used_sectioned_ui:
        fallback_candidates = _nav_candidates(
            ctx,
            query,
            limit=max(1, int(args.limit)),
            include_context=not bool(args.no_context),
            include_database=not bool(args.no_database),
        )
        if not _interactive_tty():
            print("Navigator requires an interactive TTY.", file=sys.stderr)
            return 1
        candidate = _select_numbered_nav_candidate(
            ctx,
            fallback_candidates,
            preview_lines=max(1, int(args.preview_lines)),
        )
        if candidate is None:
            return 1
        if _should_persist_last_selection(candidate.entry):
            _set_last_selection(ctx.profile_slug, candidate.entry.entry_id, candidate.entry.display_name)
        command = candidate.body.strip() or _entry_text(ctx, candidate.entry).strip()
        if mode == "return":
            return _emit_nav_selection(command)
        edited = _edit_command_text(command)
        return _run_command_text(ctx, candidate.entry, edited, yes_risk=False, usage_source="cli-nav")
    if outcome is None:
        return 1
    if outcome.action == "save_new":
        text_to_save = outcome.command_text
        print()
        print("Save as new workflow file")
        if text_to_save:
            preview = text_to_save[:60] + ("..." if len(text_to_save) > 60 else "")
            print(f"  Contents: {preview}")
        print()
        try:
            name = input("  Name: ").strip()
        except (EOFError, KeyboardInterrupt):
            name = ""
        if name:
            try:
                description = input("  Description (Enter to skip): ").strip()
            except (EOFError, KeyboardInterrupt):
                description = ""
            _create_workflow_file(ctx, name, text_to_save, description)
        else:
            print("  Cancelled.")
        return 0
    if _should_persist_last_selection(outcome.candidate.entry if outcome.candidate is not None else None):
        _set_last_selection(ctx.profile_slug, outcome.candidate.entry.entry_id, outcome.candidate.entry.display_name)
    if outcome.action == "select":
        return _emit_nav_selection(outcome.command_text)
    return _run_command_text(
        ctx,
        outcome.candidate.entry if outcome.candidate is not None else None,
        outcome.command_text,
        yes_risk=False,
        usage_source="cli-nav",
    )


def _handle_favorites(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()
    entries = [
        entry
        for entry in _workflow_entries(ctx)
        if has_tag(split_tags(entry.tag_text), FAVORITES_TAG) and _query_matches_entry(ctx, entry, query)
    ]
    return _print_find(entries[: max(1, args.limit)], as_json=args.json)


def _handle_workspace(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    query = args.query if isinstance(args.query, str) else " ".join(args.query).strip()
    entries = [entry for entry in _workflow_entries(ctx) if _query_matches_entry(ctx, entry, query)]
    if args.json:
        return _print_find(entries[: max(1, args.limit)], as_json=True)
    return _print_workspace(ctx, entries[: max(1, args.limit)])


def _handle_preview(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    entry_id = str(args.entry_id or "").strip()
    selector = str(args.selector or "").strip()
    if not entry_id and not selector:
        print("Provide --entry-id or a selector.", file=sys.stderr)
        return 2
    if entry_id:
        entry = ctx.repository.entry_from_id(entry_id, ctx.tags, ctx.snip_types, include_trashed=False)
        if entry is None:
            print(f"No entry found for id: {entry_id}", file=sys.stderr)
            return 2
    else:
        try:
            entry = _resolve_entry(ctx, selector, last_selection_entry_id=_last_selection_entry_id(ctx.profile_slug))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    print(
        _format_entry_preview_with_context(
            ctx,
            entry,
            max_lines=max(1, int(args.lines)),
            source_label=str(getattr(args, "source_label", "") or "").strip(),
            reason=str(getattr(args, "reason", "") or "").strip(),
        )
    )
    return 0


def _handle_show(args: argparse.Namespace) -> int:
    ctx = _context(args.profile)
    try:
        entry = _resolve_entry(ctx, args.selector, last_selection_entry_id=_last_selection_entry_id(ctx.profile_slug))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _set_last_selection(ctx.profile_slug, entry.entry_id, entry.display_name)
    body = _entry_text(ctx, entry)
    if args.json:
        payload = {
            "entry_id": entry.entry_id,
            "name": entry.display_name,
            "snip_type": entry.snip_type,
            "family": entry.family_key,
            "tags": entry.tag_text,
            "catalog_only": entry.catalog_only,
            "dangerous": entry.dangerous,
            "body": body,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(f"Name: {entry.display_name}")
    print(f"Entry: {entry.entry_id}")
    print(f"Type: {entry.snip_type}")
    print(f"Family: {entry.family_key or '-'}")
    print(f"Tags: {entry.tag_text or '-'}")
    print(f"Dangerous: {'yes' if entry.dangerous else 'no'}")
    print("")
    print(body)
    return 0
