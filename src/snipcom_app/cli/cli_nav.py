from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .cli_context import CliContext
from .cli_entries import _format_entry_preview_with_context
from .nav_ai import _generate_cli_ai_candidate
from .nav_providers import (
    NavigatorAIState,
    NavigatorCandidate,
    NavigatorOutcome,
    NavigatorSection,
    _nav_candidates,
)
from .nav_tui import _curses_nav_session, _run_curses_on_terminal


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _nav_outcome(
    ctx: CliContext,
    query: str,
    *,
    limit: int,
    include_context: bool,
    include_database: bool,
    mode: str,
) -> tuple[bool, NavigatorOutcome | None]:
    return _run_curses_on_terminal(
        _curses_nav_session,
        ctx,
        initial_query=query,
        limit=limit,
        include_context=include_context,
        include_database=include_database,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Fallback numbered picker
# ---------------------------------------------------------------------------

def _select_numbered_nav_candidate(
    ctx: CliContext,
    candidates: list[NavigatorCandidate],
    *,
    preview_lines: int,
) -> NavigatorCandidate | None:
    if not candidates:
        return None
    while True:
        for index, candidate in enumerate(candidates, start=1):
            reason = f" - {candidate.reason}" if candidate.reason else ""
            print(f"{index:2d}. [{candidate.source_label}] {candidate.entry.display_name}{reason}")
        choice = input("Select entry number (blank to cancel): ").strip()
        if not choice:
            return None
        try:
            selected_index = int(choice)
        except ValueError:
            print("Invalid number. Try again.", file=sys.stderr)
            continue
        if selected_index < 1 or selected_index > len(candidates):
            print("Selection out of range. Try again.", file=sys.stderr)
            continue
        selected = candidates[selected_index - 1]
        print("")
        print(
            _format_entry_preview_with_context(
                ctx,
                selected.entry,
                max_lines=preview_lines,
                source_label=selected.source_label,
                reason=selected.reason,
            )
        )
        print("")
        confirm = input("Use this entry? [Enter=yes, n=reselect, q=cancel]: ").strip().casefold()
        if confirm in {"", "y", "yes"}:
            return selected
        if confirm in {"q", "quit", "c", "cancel"}:
            return None
        print("")
