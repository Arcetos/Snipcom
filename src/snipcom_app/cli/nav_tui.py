from __future__ import annotations

import curses
import os
import textwrap
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.cli_nav_settings import CliNavSettings

from .cli_context import CliContext
from .cli_entries import _entry_text, _interactive_tty
from .cli_handlers_write import _create_workflow_file
from .nav_ai import _refresh_ai_state
from .nav_providers import (
    NAV_PAIR_AI,
    NAV_PAIR_DEFAULT,
    NAV_PAIR_GHOST,
    NAV_PAIR_HEADER,
    NAV_PAIR_HEURISTIC,
    NAV_PAIR_INPUT,
    NAV_PAIR_STATUS,
    NAV_PAIR_WORKFLOW,
    NavigatorAIState,
    NavigatorCandidate,
    NavigatorOutcome,
    NavigatorSection,
    _candidate_command_text,
    _candidate_description_text,
    _candidate_return_text,
    _nav_sections,
)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

_CURSES_COLOR_MAP: dict[str, int] = {}


def _curses_color(name: str) -> int:
    """Lazily map color name string to curses color constant. -1 = default terminal."""
    if not _CURSES_COLOR_MAP:
        _CURSES_COLOR_MAP.update({
            "default": -1,
            "black": curses.COLOR_BLACK,
            "red": curses.COLOR_RED,
            "green": curses.COLOR_GREEN,
            "yellow": curses.COLOR_YELLOW,
            "blue": curses.COLOR_BLUE,
            "magenta": curses.COLOR_MAGENTA,
            "cyan": curses.COLOR_CYAN,
            "white": curses.COLOR_WHITE,
        })
    return _CURSES_COLOR_MAP.get(name.lower(), curses.COLOR_WHITE)


def _init_nav_colors(stdscr: curses.window, nav_settings: "CliNavSettings") -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    use_default_background = False
    try:
        curses.use_default_colors()
        use_default_background = True
    except curses.error:
        pass
    background = -1 if use_default_background else curses.COLOR_BLACK
    c = nav_settings.colors
    curses.init_pair(NAV_PAIR_DEFAULT, curses.COLOR_WHITE, background)
    curses.init_pair(NAV_PAIR_INPUT, _curses_color(c.input), background)
    curses.init_pair(NAV_PAIR_HEADER, curses.COLOR_WHITE, background)
    curses.init_pair(NAV_PAIR_WORKFLOW, _curses_color(c.workflow), background)
    curses.init_pair(NAV_PAIR_HEURISTIC, _curses_color(c.heuristic), background)
    curses.init_pair(NAV_PAIR_AI, _curses_color(c.ai), background)
    curses.init_pair(NAV_PAIR_STATUS, curses.COLOR_GREEN, background)
    curses.init_pair(NAV_PAIR_GHOST, curses.COLOR_WHITE, background)
    stdscr.bkgdset(" ", curses.color_pair(NAV_PAIR_DEFAULT))
    stdscr.attrset(curses.color_pair(NAV_PAIR_DEFAULT))


def _section_pair(source_label: str) -> int:
    cleaned = source_label.strip().casefold()
    if cleaned == "workflow":
        return NAV_PAIR_WORKFLOW
    if cleaned in {"heuristic", "context", "database"}:
        return NAV_PAIR_HEURISTIC
    if cleaned == "ai":
        return NAV_PAIR_AI
    return NAV_PAIR_DEFAULT


def _section_title_attr(source_label: str, *, selected: bool) -> int:
    base = curses.color_pair(_section_pair(source_label)) | curses.A_BOLD
    if selected:
        return base | curses.A_UNDERLINE
    return base


def _row_attr(candidate: NavigatorCandidate, *, selected: bool) -> int:
    base = curses.color_pair(_section_pair(candidate.source_label))
    if selected:
        return base | curses.A_REVERSE | curses.A_BOLD
    return base


# ---------------------------------------------------------------------------
# Safe drawing
# ---------------------------------------------------------------------------

def _safe_addstr(stdscr: curses.window, y: int, x: int, text: str, attr: int = 0) -> None:
    if y < 0 or x < 0:
        return
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        return


def _safe_hline(stdscr: curses.window, y: int, x: int, ch: int, width: int) -> None:
    if y < 0 or x < 0 or width <= 0:
        return
    try:
        stdscr.hline(y, x, ch, width)
    except curses.error:
        return


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def _trim_cell(text: str, width: int) -> str:
    cleaned = " ".join(str(text).split())
    if width <= 0:
        return ""
    if len(cleaned) <= width:
        return cleaned.ljust(width)
    if width == 1:
        return cleaned[:1]
    return f"{cleaned[: max(0, width - 1)]}~"


def _wrap_cell_lines(text: str, width: int) -> list[str]:
    cleaned = " ".join(str(text).split())
    if width <= 0:
        return [""]
    if not cleaned:
        return [""]
    wrapped = textwrap.wrap(
        cleaned,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return wrapped or [cleaned[:width]]


# ---------------------------------------------------------------------------
# Legacy layout helpers (kept for compatibility)
# ---------------------------------------------------------------------------

def _nav_table_widths(screen_width: int) -> tuple[int, int, int, int]:
    available = max(40, screen_width - 2)
    command_width = max(16, int(available * 0.40))
    description_width = max(14, int(available * 0.24))
    name_width = max(14, int(available * 0.20))
    used = command_width + description_width + name_width + 3
    family_width = max(10, available - used)
    return command_width, description_width, name_width, family_width


def _row_columns(candidate: NavigatorCandidate) -> tuple[str, str, str, str]:
    return (
        _candidate_command_text(candidate),
        _candidate_description_text(candidate, {}),
        candidate.entry.display_name,
        candidate.entry.family_key or candidate.entry.snip_type,
    )


def _row_height(candidate: NavigatorCandidate, widths: tuple[int, int, int, int]) -> int:
    columns = _row_columns(candidate)
    return max(len(_wrap_cell_lines(text, width)) for text, width in zip(columns, widths, strict=True))


def _section_visible_rows(
    section: NavigatorSection,
    *,
    selected_candidate_index: int | None,
    line_budget: int,
    widths: tuple[int, int, int, int],
) -> tuple[int, list[tuple[int, NavigatorCandidate, int]]]:
    if not section.candidates:
        return 0, []
    safe_budget = max(1, line_budget)
    selected_index = 0 if selected_candidate_index is None else max(0, min(selected_candidate_index, len(section.candidates) - 1))
    offset = 0
    while offset < selected_index:
        lines_used = 0
        for probe_index in range(offset, selected_index + 1):
            lines_used += _row_height(section.candidates[probe_index], widths)
            if lines_used > safe_budget:
                offset += 1
                break
        else:
            break

    visible: list[tuple[int, NavigatorCandidate, int]] = []
    lines_used = 0
    for row_index in range(offset, len(section.candidates)):
        candidate = section.candidates[row_index]
        row_height = _row_height(candidate, widths)
        if visible and lines_used + row_height > safe_budget:
            break
        if not visible and row_height > safe_budget:
            visible.append((row_index, candidate, safe_budget))
            break
        visible.append((row_index, candidate, row_height))
        lines_used += row_height
        if lines_used >= safe_budget:
            break
    return offset, visible


# ---------------------------------------------------------------------------
# Column layout (settings-driven)
# ---------------------------------------------------------------------------

def _nav_col_widths(screen_width: int, nav_settings: "CliNavSettings") -> list[int]:
    """Convert column width_pct to absolute character widths fitted to screen."""
    cols = nav_settings.columns
    if not cols:
        return []
    available = max(40, screen_width - 1)  # -1 for marker char
    total_pct = sum(c.width_pct for c in cols)
    widths = [max(4, int(available * c.width_pct / total_pct)) for c in cols]
    # Assign any leftover to the last column
    used = sum(widths)
    if used < available:
        widths[-1] += available - used
    return widths


def _col_value(candidate: NavigatorCandidate, key: str, descriptions: dict[str, str]) -> str:
    entry = candidate.entry
    if key == "command":
        return _candidate_command_text(candidate)
    if key == "description":
        return _candidate_description_text(candidate, descriptions)
    if key == "name":
        return entry.display_name
    if key == "tag":
        return entry.tag_text
    if key == "family":
        return entry.family_key
    if key == "dangerous":
        return "!" if entry.dangerous else ""
    return ""


# ---------------------------------------------------------------------------
# Row and screen drawing
# ---------------------------------------------------------------------------

def _draw_nav_row(
    stdscr: curses.window,
    y: int,
    candidate: NavigatorCandidate,
    *,
    col_widths: list[int],
    nav_settings: "CliNavSettings",
    selected: bool,
    descriptions: dict[str, str],
) -> int:
    """Draw one candidate row. Returns number of screen lines consumed (1 or 2)."""
    attr = _row_attr(candidate, selected=selected)
    marker = ">" if selected else " "
    wrap = nav_settings.wrap_text

    # Build raw values per column
    values = [_col_value(candidate, col.key, descriptions) for col in nav_settings.columns]

    if not wrap:
        parts = [marker]
        for val, width in zip(values, col_widths):
            parts.append(_trim_cell(val, width))
        _safe_addstr(stdscr, y, 0, " ".join(parts), attr)
        return 1

    # Wrap mode: up to 2 lines per row
    line1_parts = [marker]
    line2_parts = [" "]
    has_overflow = False
    for val, width in zip(values, col_widths):
        cleaned = " ".join(str(val).split())
        if len(cleaned) <= width:
            line1_parts.append(cleaned.ljust(width))
            line2_parts.append(" " * width)
        else:
            line1_parts.append(cleaned[:width])
            overflow = cleaned[width:2 * width].strip()
            line2_parts.append(overflow.ljust(width) if overflow else " " * width)
            if overflow:
                has_overflow = True
    _safe_addstr(stdscr, y, 0, " ".join(line1_parts), attr)
    if has_overflow:
        _safe_addstr(stdscr, y + 1, 0, " ".join(line2_parts), attr | curses.A_DIM)
        return 2
    return 1


def _draw_nav_screen(
    stdscr: curses.window,
    *,
    sections: list[NavigatorSection],
    mode: str,
    edit_mode: bool,
    buffer_text: str,
    selected_section_index: int,
    selected_candidate_index: int,
    descriptions: dict[str, str],
    nav_settings: "CliNavSettings",
) -> None:
    height, width = stdscr.getmaxyx()
    col_widths = _nav_col_widths(width, nav_settings)
    stdscr.erase()

    # Reserve bottom 2 lines for input + status
    content_height = max(0, height - 2)
    input_y = max(0, height - 2)
    status_y = max(0, height - 1)

    lim = nav_settings.section_limits
    # Extract section candidates
    heuristic_cands = sections[0].candidates if sections else []
    ai_cands = sections[1].candidates[:lim.ai_max] if len(sections) > 1 else []
    workflow_cands = sections[2].candidates if len(sections) > 2 else []

    # AI status row when no candidates
    ai_status_msg = ""
    if not ai_cands and len(sections) > 1:
        msg = sections[1].empty_message
        if msg and msg != "[no results]":
            ai_status_msg = msg

    # Each row may consume 1 or 2 lines when wrap_text is on
    lines_per_row = 2 if nav_settings.wrap_text else 1
    # Dynamic allocation: workflow = all, ai = all (≤ai_max), heuristic fills rest (min heuristic_min)
    workflow_show = len(workflow_cands)
    ai_show = len(ai_cands)
    ai_status_rows = 1 if ai_status_msg else 0
    remaining = content_height - workflow_show * lines_per_row - ai_show * lines_per_row - ai_status_rows
    heuristic_count = len(heuristic_cands)
    heuristic_min = min(lim.heuristic_min, heuristic_count) if heuristic_count > 0 else 0
    heuristic_show = max(heuristic_min, min(heuristic_count, max(0, remaining // lines_per_row)))

    # Scroll offset: keep selected candidate visible within its show_count
    def _scroll_offset(sec_idx: int, show_count: int, cands: list) -> int:
        if sec_idx != selected_section_index or not cands or show_count <= 0:
            return 0
        sel = min(selected_candidate_index, len(cands) - 1)
        return max(0, sel - show_count + 1)

    h_offset = _scroll_offset(0, heuristic_show, heuristic_cands)
    ai_offset = _scroll_offset(1, ai_show, ai_cands)
    w_offset = _scroll_offset(2, workflow_show, workflow_cands)

    y = 0

    # Heuristic section
    for i in range(heuristic_show):
        if y >= content_height:
            break
        idx = h_offset + i
        if idx >= len(heuristic_cands):
            break
        is_sel = selected_section_index == 0 and selected_candidate_index == idx
        y += _draw_nav_row(stdscr, y, heuristic_cands[idx], col_widths=col_widths, nav_settings=nav_settings, selected=is_sel, descriptions=descriptions)

    # AI section
    for i in range(ai_show):
        if y >= content_height:
            break
        idx = ai_offset + i
        if idx >= len(ai_cands):
            break
        is_sel = selected_section_index == 1 and selected_candidate_index == idx
        y += _draw_nav_row(stdscr, y, ai_cands[idx], col_widths=col_widths, nav_settings=nav_settings, selected=is_sel, descriptions=descriptions)

    if ai_status_msg and y < content_height:
        _safe_addstr(stdscr, y, 1, ai_status_msg[: max(0, width - 2)],
                     curses.color_pair(NAV_PAIR_AI) | curses.A_DIM)
        y += 1

    # Workflow section
    for i in range(workflow_show):
        if y >= content_height:
            break
        idx = w_offset + i
        if idx >= len(workflow_cands):
            break
        is_sel = selected_section_index == 2 and selected_candidate_index == idx
        y += _draw_nav_row(stdscr, y, workflow_cands[idx], col_widths=col_widths, nav_settings=nav_settings, selected=is_sel, descriptions=descriptions)

    # Input line at bottom
    prompt = "> "
    prompt_attr = curses.color_pair(NAV_PAIR_INPUT) | curses.A_BOLD
    if edit_mode:
        prompt_attr |= curses.A_UNDERLINE
    _safe_addstr(stdscr, input_y, 0, prompt, prompt_attr)
    _safe_addstr(stdscr, input_y, len(prompt), buffer_text[: max(0, width - len(prompt) - 1)],
                 curses.color_pair(NAV_PAIR_INPUT))

    # Ghost suggestion on input line
    ghost = _ghost_suggestion(sections, buffer_text)
    if ghost and not edit_mode:
        typed_len = len(buffer_text)
        remainder = ghost[typed_len:] if ghost.casefold().startswith(buffer_text.casefold()) else ghost
        ghost_x = len(prompt) + typed_len
        _safe_addstr(stdscr, input_y, ghost_x,
                     remainder[: max(0, width - ghost_x - 1)],
                     curses.color_pair(NAV_PAIR_GHOST) | curses.A_DIM)

    # Status line
    status = _nav_status_line(mode=mode, edit_mode=edit_mode)
    _safe_addstr(stdscr, status_y, 0, status[: max(0, width - 1)], curses.color_pair(NAV_PAIR_STATUS))


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _nav_status_line(*, mode: str, edit_mode: bool) -> str:
    if mode == "return":
        if edit_mode:
            return "Enter return edited command | Esc cancel edit | arrows move cursor"
        return "Enter select | Tab edit | Esc cancel | Left/Right section | Up/Down row"
    if edit_mode:
        return "Enter execute | Alt+S save new | Esc exit | arrows move cursor"
    return "Enter execute | Tab edit | Shift+Tab ghost | Esc exit | Left/Right section | Up/Down row"


def _move_cursor_left(cursor_index: int) -> int:
    return max(0, cursor_index - 1)


def _move_cursor_right(cursor_index: int, buffer_text: str) -> int:
    return min(len(buffer_text), cursor_index + 1)


def _delete_before_cursor(buffer_text: str, cursor_index: int) -> tuple[str, int]:
    if cursor_index <= 0:
        return buffer_text, cursor_index
    return buffer_text[: cursor_index - 1] + buffer_text[cursor_index:], cursor_index - 1


def _insert_at_cursor(buffer_text: str, cursor_index: int, text: str) -> tuple[str, int]:
    updated = buffer_text[:cursor_index] + text + buffer_text[cursor_index:]
    return updated, cursor_index + len(text)


def _ghost_suggestion(sections: list[NavigatorSection], buffer_text: str) -> str:
    """Return the top candidate's command text as ghost hint, or '' if none."""
    for section in sections:
        for candidate in section.candidates:
            cmd = _candidate_command_text(candidate)
            if not cmd:
                continue
            if not buffer_text.strip():
                return cmd
            if cmd.casefold().startswith(buffer_text.strip().casefold()):
                return cmd
    return ""


# ---------------------------------------------------------------------------
# Cursor helper
# ---------------------------------------------------------------------------

def _current_candidate(
    sections: list[NavigatorSection],
    section_index: int,
    candidate_index: int,
) -> NavigatorCandidate | None:
    if not sections:
        return None
    section_index = max(0, min(section_index, len(sections) - 1))
    candidates = sections[section_index].candidates
    if not candidates:
        return None
    candidate_index = max(0, min(candidate_index, len(candidates) - 1))
    return candidates[candidate_index]


# ---------------------------------------------------------------------------
# Session loop
# ---------------------------------------------------------------------------

def _curses_nav_session(
    stdscr: curses.window,
    ctx: CliContext,
    *,
    initial_query: str,
    limit: int,
    include_context: bool,
    include_database: bool,
    mode: str,
) -> NavigatorOutcome | None:
    browse_query = initial_query
    buffer_text = initial_query
    cursor_index = len(buffer_text)
    selected_section_index = 0
    selected_candidate_index = 0
    edit_mode = False
    ai_state = NavigatorAIState()
    last_keystroke_time: float = 0.0
    _AI_DEBOUNCE_SECS = 0.45
    descriptions: dict[str, str] = ctx.repository.load_descriptions()

    from ..core.cli_nav_settings import load_cli_nav_settings as _load_nav_settings
    nav_settings = _load_nav_settings(ctx.settings)

    import curses as _curses_mod

    def _resolve_key(s: str) -> "int | str | None":
        """Map a stored key name to a curses key value."""
        if not s.strip():
            return None
        _MAP = {
            "up": _curses_mod.KEY_UP,
            "down": _curses_mod.KEY_DOWN,
            "left": _curses_mod.KEY_LEFT,
            "right": _curses_mod.KEY_RIGHT,
            "shift+tab": _curses_mod.KEY_BTAB,
            "btab": _curses_mod.KEY_BTAB,
            "tab": "\t",
            "backspace": _curses_mod.KEY_BACKSPACE,
        }
        # Handle Alt+<char>: store as "\x1b<char>"
        normalized = s.strip().lower()
        if normalized.startswith("alt+") and len(normalized) == 5:
            return "\x1b" + normalized[4]
        if normalized in _MAP:
            return _MAP[normalized]
        if len(s.strip()) == 1:
            return s.strip()
        return None

    def _key_set(binding: list[str]) -> set:
        result = set()
        for s in binding:
            v = _resolve_key(s)
            if v is not None:
                result.add(v)
        return result

    kb = nav_settings.key_bindings
    _keys_up          = _key_set(kb.nav_up)       or {curses.KEY_UP}
    _keys_down        = _key_set(kb.nav_down)      or {curses.KEY_DOWN}
    _keys_left        = _key_set(kb.nav_left)      or {curses.KEY_LEFT}
    _keys_right       = _key_set(kb.nav_right)     or {curses.KEY_RIGHT}
    _keys_tab_fill    = _key_set(kb.tab_fill)       or {"\t"}
    _keys_accept_ghost = _key_set(kb.accept_ghost) or {curses.KEY_BTAB}
    _keys_save_new    = _key_set(kb.save_new)       or {"\x1bs"}
    _keys_quit        = _key_set(kb.quit_nav)       or {"q"}

    _init_nav_colors(stdscr, nav_settings)
    try:
        curses.curs_set(1)
    except curses.error:
        pass
    stdscr.keypad(True)
    stdscr.timeout(150)

    while True:
        # Fast non-blocking check before expensive rendering — exit on bare Esc immediately.
        stdscr.timeout(0)
        try:
            _fast_key = stdscr.get_wch()
        except curses.error:
            _fast_key = None
        stdscr.timeout(150)
        if _fast_key == "\x1b":
            stdscr.timeout(10)
            try:
                _follow = stdscr.get_wch()
            except curses.error:
                _follow = None
            finally:
                stdscr.timeout(150)
            if _follow is None:
                stdscr.clear()
                stdscr.refresh()
                return None
            if isinstance(_follow, str):
                _fast_key = "\x1b" + _follow
            else:
                stdscr.clear()
                stdscr.refresh()
                return None

        query_text = browse_query if edit_mode else buffer_text
        _now = time.monotonic()
        if _now - last_keystroke_time >= _AI_DEBOUNCE_SECS:
            _refresh_ai_state(ctx, query_text, ai_state)
        sections = _nav_sections(
            ctx,
            query_text,
            limit=limit,
            include_context=include_context,
            include_database=include_database,
            ai_state=ai_state,
        )
        if sections:
            selected_section_index = max(0, min(selected_section_index, len(sections) - 1))
        active_candidates = sections[selected_section_index].candidates if sections else []
        if active_candidates:
            selected_candidate_index = max(0, min(selected_candidate_index, len(active_candidates) - 1))
        else:
            selected_candidate_index = 0
        _draw_nav_screen(
            stdscr,
            sections=sections,
            mode=mode,
            edit_mode=edit_mode,
            buffer_text=buffer_text,
            selected_section_index=selected_section_index,
            selected_candidate_index=selected_candidate_index,
            descriptions=descriptions,
            nav_settings=nav_settings,
        )
        try:
            _h, _w = stdscr.getmaxyx()
            stdscr.move(max(0, _h - 2), min(2 + cursor_index, max(0, _w - 1)))
        except curses.error:
            pass
        stdscr.refresh()

        if _fast_key is not None:
            key = _fast_key
        else:
            try:
                key = stdscr.get_wch()
            except curses.error:
                continue
        last_keystroke_time = time.monotonic()

        if key == "\x1b":
            # Peek ahead with a very short timeout to distinguish Alt+char from bare Esc.
            stdscr.timeout(10)
            try:
                follow = stdscr.get_wch()
            except curses.error:
                follow = None
            finally:
                stdscr.timeout(150)
            if follow is None:
                # Clear the screen before wrapper calls endwin() so the terminal looks clean instantly.
                stdscr.clear()
                stdscr.refresh()
                return None
            if isinstance(follow, str):
                key = "\x1b" + follow  # reassemble as Alt+char and fall through
            else:
                return None  # unexpected special key after Esc — exit

        if edit_mode:
            if key in ("\n", "\r", curses.KEY_ENTER):
                command_text = buffer_text.strip()
                candidate = _current_candidate(sections, selected_section_index, selected_candidate_index)
                if command_text:
                    action = "select" if mode == "return" else "execute"
                    return NavigatorOutcome(action=action, candidate=candidate, command_text=command_text)
                continue
            if key in _keys_save_new:  # Alt+S in edit mode — signal caller to run save flow after curses exits
                return NavigatorOutcome(action="save_new", candidate=None, command_text=buffer_text.strip())
            if key in (curses.KEY_LEFT,):
                cursor_index = _move_cursor_left(cursor_index)
                continue
            if key in (curses.KEY_RIGHT,):
                cursor_index = _move_cursor_right(cursor_index, buffer_text)
                continue
            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                buffer_text, cursor_index = _delete_before_cursor(buffer_text, cursor_index)
                continue
            if isinstance(key, str) and key.isprintable() and key not in {"\n", "\r", "\t"}:
                buffer_text, cursor_index = _insert_at_cursor(buffer_text, cursor_index, key)
                continue
            continue

        if key in _keys_up:
            if active_candidates:
                if selected_candidate_index > 0:
                    selected_candidate_index -= 1
                else:
                    for prev_sec in range(selected_section_index - 1, -1, -1):
                        if sections[prev_sec].candidates:
                            selected_section_index = prev_sec
                            selected_candidate_index = len(sections[prev_sec].candidates) - 1
                            break
            continue
        if key in _keys_down:
            if active_candidates:
                if selected_candidate_index < len(active_candidates) - 1:
                    selected_candidate_index += 1
                else:
                    for next_sec in range(selected_section_index + 1, len(sections)):
                        if sections[next_sec].candidates:
                            selected_section_index = next_sec
                            selected_candidate_index = 0
                            break
            continue
        if key in _keys_left:
            if sections:
                selected_section_index = max(0, selected_section_index - 1)
                next_candidates = sections[selected_section_index].candidates
                selected_candidate_index = min(selected_candidate_index, max(0, len(next_candidates) - 1))
            continue
        if key in _keys_right:
            if sections:
                selected_section_index = min(len(sections) - 1, selected_section_index + 1)
                next_candidates = sections[selected_section_index].candidates
                selected_candidate_index = min(selected_candidate_index, max(0, len(next_candidates) - 1))
            continue
        if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            if buffer_text:
                buffer_text, cursor_index = _delete_before_cursor(buffer_text, cursor_index)
                selected_candidate_index = 0
            continue
        if key in ("\n", "\r", curses.KEY_ENTER):
            candidate = _current_candidate(sections, selected_section_index, selected_candidate_index)
            if mode == "return":
                if candidate is not None:
                    return NavigatorOutcome(action="select", candidate=candidate,
                                            command_text=_candidate_return_text(candidate))
            elif mode == "execute":
                if candidate is not None:
                    return NavigatorOutcome(action="execute", candidate=candidate,
                                            command_text=_candidate_return_text(candidate))
                if buffer_text.strip():
                    return NavigatorOutcome(action="execute", candidate=None,
                                            command_text=buffer_text.strip())
            continue
        if key in _keys_tab_fill:
            candidate = _current_candidate(sections, selected_section_index, selected_candidate_index)
            if candidate is None:
                continue
            browse_query = buffer_text
            buffer_text = (candidate.body.strip() or _entry_text(ctx, candidate.entry).strip() or candidate.entry.display_name)
            cursor_index = len(buffer_text)
            edit_mode = True
            continue
        if key in _keys_accept_ghost:  # Shift+Tab — accept ghost suggestion
            ghost = _ghost_suggestion(sections, buffer_text)
            if ghost:
                buffer_text = ghost
                cursor_index = len(buffer_text)
                selected_candidate_index = 0
            continue
        if key in _keys_save_new:  # Alt+S — save current input as a new workflow file
            import time as _time
            curses.def_prog_mode()
            curses.endwin()
            try:
                text_to_save = buffer_text.strip()
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
                _time.sleep(0.8)
            finally:
                stdscr.refresh()
            continue

        if isinstance(key, str):
            if key in _keys_quit and not buffer_text:
                return None
            if key.isprintable() and key not in {"\n", "\r", "\t"}:
                buffer_text, cursor_index = _insert_at_cursor(buffer_text, cursor_index, key)
                selected_candidate_index = 0
            continue

    return None


def _run_curses_on_terminal(callback, *args, **kwargs):
    if _interactive_tty():
        return True, curses.wrapper(callback, *args, **kwargs)
    try:
        tty_fd = os.open("/dev/tty", os.O_RDWR)
    except OSError:
        return False, None
    saved_fds = [os.dup(0), os.dup(1), os.dup(2)]
    try:
        os.dup2(tty_fd, 0)
        os.dup2(tty_fd, 1)
        os.dup2(tty_fd, 2)
        return True, curses.wrapper(callback, *args, **kwargs)
    except curses.error:
        return False, None
    finally:
        for target_fd, saved_fd in enumerate(saved_fds):
            try:
                os.dup2(saved_fd, target_fd)
            finally:
                os.close(saved_fd)
        os.close(tty_fd)
