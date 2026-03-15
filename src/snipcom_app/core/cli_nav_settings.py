from __future__ import annotations

from dataclasses import dataclass, field

VALID_COLUMN_KEYS: tuple[str, ...] = (
    "command", "name", "description", "tag", "family", "dangerous",
)
VALID_COLOR_NAMES: tuple[str, ...] = (
    "default", "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
)


@dataclass
class NavColumn:
    key: str        # one of VALID_COLUMN_KEYS
    width_pct: int  # 1–100, percentage of terminal width


@dataclass
class NavColors:
    input: str     = "cyan"
    workflow: str  = "cyan"
    heuristic: str = "yellow"
    ai: str        = "magenta"


@dataclass
class NavSectionLimits:
    heuristic_min: int = 3
    ai_max: int        = 5
    workflow_min: int  = 3


# Friendly key names that resolve to curses keys in nav_tui.py.
# Values use these canonical names: Up, Down, Left, Right, Tab, Shift+Tab,
# Alt+<char> (e.g. Alt+s), or any single printable character (e.g. j, k, q).
NAV_KEY_BINDING_DEFAULTS: dict[str, list[str]] = {
    "nav_up":        ["Up", ""],
    "nav_down":      ["Down", ""],
    "nav_left":      ["Left", ""],
    "nav_right":     ["Right", ""],
    "tab_fill":      ["Tab", ""],
    "accept_ghost":  ["Shift+Tab", ""],
    "save_new":      ["Alt+s", ""],
    "quit_nav":      ["q", ""],
}
NAV_KEY_BINDING_LABELS: dict[str, str] = {
    "nav_up":       "Move up",
    "nav_down":     "Move down",
    "nav_left":     "Previous section",
    "nav_right":    "Next section",
    "tab_fill":     "Fill from selected",
    "accept_ghost": "Accept ghost suggestion",
    "save_new":     "Save input as new file",
    "quit_nav":     "Quit (when input empty)",
}


@dataclass
class NavKeyBindings:
    nav_up:       list[str] = field(default_factory=lambda: ["Up", ""])
    nav_down:     list[str] = field(default_factory=lambda: ["Down", ""])
    nav_left:     list[str] = field(default_factory=lambda: ["Left", ""])
    nav_right:    list[str] = field(default_factory=lambda: ["Right", ""])
    tab_fill:     list[str] = field(default_factory=lambda: ["Tab", ""])
    accept_ghost: list[str] = field(default_factory=lambda: ["Shift+Tab", ""])
    save_new:     list[str] = field(default_factory=lambda: ["Alt+s", ""])
    quit_nav:     list[str] = field(default_factory=lambda: ["q", ""])


def _default_columns() -> list[NavColumn]:
    return [
        NavColumn("command", 42),
        NavColumn("description", 32),
        NavColumn("name", 20),
    ]


@dataclass
class CliNavSettings:
    columns: list[NavColumn]          = field(default_factory=_default_columns)
    colors: NavColors                 = field(default_factory=NavColors)
    section_limits: NavSectionLimits  = field(default_factory=NavSectionLimits)
    wrap_text: bool                   = False
    key_bindings: NavKeyBindings      = field(default_factory=NavKeyBindings)


DEFAULT_CLI_NAV_SETTINGS = CliNavSettings(
    columns=_default_columns(),
    colors=NavColors(),
    section_limits=NavSectionLimits(),
    wrap_text=False,
    key_bindings=NavKeyBindings(),
)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def load_cli_nav_settings(settings_dict: dict) -> CliNavSettings:
    """Extract 'cli_nav' sub-dict from profile settings; return defaults on any error."""
    raw = settings_dict.get("cli_nav")
    if not isinstance(raw, dict):
        return CliNavSettings(
            columns=_default_columns(),
            colors=NavColors(),
            section_limits=NavSectionLimits(),
        )

    # --- columns ---
    columns: list[NavColumn] = []
    for col in raw.get("columns", []):
        if not isinstance(col, dict):
            continue
        key = str(col.get("key", ""))
        if key not in VALID_COLUMN_KEYS:
            continue
        try:
            pct = _clamp(int(col.get("width_pct", 20)), 1, 100)
        except (TypeError, ValueError):
            pct = 20
        columns.append(NavColumn(key, pct))
    if not columns:
        columns = _default_columns()

    # --- colors ---
    raw_colors = raw.get("colors", {})
    if not isinstance(raw_colors, dict):
        raw_colors = {}

    def _safe_color(val: object, default: str) -> str:
        s = str(val).strip().lower() if val is not None else ""
        return s if s in VALID_COLOR_NAMES else default

    colors = NavColors(
        input=_safe_color(raw_colors.get("input"), "cyan"),
        workflow=_safe_color(raw_colors.get("workflow"), "cyan"),
        heuristic=_safe_color(raw_colors.get("heuristic"), "yellow"),
        ai=_safe_color(raw_colors.get("ai"), "magenta"),
    )

    # --- section_limits ---
    raw_limits = raw.get("section_limits", {})
    if not isinstance(raw_limits, dict):
        raw_limits = {}

    def _safe_int(val: object, default: int) -> int:
        try:
            return _clamp(int(val), 0, 20)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    section_limits = NavSectionLimits(
        heuristic_min=_safe_int(raw_limits.get("heuristic_min"), 3),
        ai_max=_safe_int(raw_limits.get("ai_max"), 5),
        workflow_min=_safe_int(raw_limits.get("workflow_min"), 3),
    )

    wrap_text = bool(raw.get("wrap_text", False))

    # --- key_bindings ---
    raw_kb = raw.get("key_bindings", {})
    if not isinstance(raw_kb, dict):
        raw_kb = {}

    def _safe_key_list(val: object, default: list[str]) -> list[str]:
        if isinstance(val, list):
            return [str(v).strip() for v in val[:2]] + [""] * (2 - min(2, len(val)))
        return list(default)

    key_bindings = NavKeyBindings(
        nav_up=_safe_key_list(raw_kb.get("nav_up"), ["Up", ""]),
        nav_down=_safe_key_list(raw_kb.get("nav_down"), ["Down", ""]),
        nav_left=_safe_key_list(raw_kb.get("nav_left"), ["Left", ""]),
        nav_right=_safe_key_list(raw_kb.get("nav_right"), ["Right", ""]),
        tab_fill=_safe_key_list(raw_kb.get("tab_fill"), ["Tab", ""]),
        accept_ghost=_safe_key_list(raw_kb.get("accept_ghost"), ["Shift+Tab", ""]),
        save_new=_safe_key_list(raw_kb.get("save_new"), ["Alt+s", ""]),
        quit_nav=_safe_key_list(raw_kb.get("quit_nav"), ["q", ""]),
    )

    return CliNavSettings(
        columns=columns,
        colors=colors,
        section_limits=section_limits,
        wrap_text=wrap_text,
        key_bindings=key_bindings,
    )


def dump_cli_nav_settings(nav: CliNavSettings) -> dict:
    """Serialize CliNavSettings to the JSON shape stored under 'cli_nav' key."""
    return {
        "columns": [{"key": c.key, "width_pct": c.width_pct} for c in nav.columns],
        "colors": {
            "input": nav.colors.input,
            "workflow": nav.colors.workflow,
            "heuristic": nav.colors.heuristic,
            "ai": nav.colors.ai,
        },
        "section_limits": {
            "heuristic_min": nav.section_limits.heuristic_min,
            "ai_max": nav.section_limits.ai_max,
            "workflow_min": nav.section_limits.workflow_min,
        },
        "wrap_text": nav.wrap_text,
        "key_bindings": {
            "nav_up": nav.key_bindings.nav_up,
            "nav_down": nav.key_bindings.nav_down,
            "nav_left": nav.key_bindings.nav_left,
            "nav_right": nav.key_bindings.nav_right,
            "tab_fill": nav.key_bindings.tab_fill,
            "accept_ghost": nav.key_bindings.accept_ghost,
            "save_new": nav.key_bindings.save_new,
            "quit_nav": nav.key_bindings.quit_nav,
        },
    }
