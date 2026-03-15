from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

from .cli_context import CliContext, DEFAULT_PREVIEW_LINES, APP_SUPPORT_DIR, _context, _last_selection_entry_id, _set_last_selection
from .cli_entries import (
    _confirm_risk_cli,
    _entry_text,
    _launcher_program,
    _record_cli_usage,
    _run_command_text,
    _workflow_entries,
)
from ..core.repository import SnipcomEntry
from ..core.safety import evaluate_command_risk
from .cli_handlers_query import (
    _handle_find,
    _handle_nav,
    _handle_favorites,
    _handle_workspace,
    _handle_preview,
    _handle_show,
)
from .cli_handlers_write import (
    _handle_new,
    _handle_cto,
    _handle_sto,
    _handle_add_from_history,
    _read_multiline_input,
    _create_workflow_file,
    _capture_terminal_output,
    _copy_to_clipboard,
)
from .cli_handlers_advanced import (
    _handle_send,
    _handle_pick,
    _handle_nat,
    _handle_shell_print,
    _handle_shell_install,
    _handle_source_add,
    _handle_source_list,
    _handle_source_refresh,
    _handle_source_import_once,
)


TOP_LEVEL_ALIASES: dict[str, tuple[str, ...]] = {
    "nav": ("nv",),
    "find": ("fd", "search"),
    "favorites": ("f", "fav"),
    "workspace": ("w", "ws"),
    "preview": ("pv",),
    "show": ("s", "view"),
    "send": ("x", "tx"),
    "add-from-history": ("h", "hist", "ah"),
    "pick": ("p", "sel"),
    "nat": ("n",),
    "shell": ("sh",),
    "source": ("src",),
    "new": (),
    "cto": (),
    "sto": (),
}
PREFIXED_TOP_LEVEL_COMMANDS: dict[str, str] = {}
for _command, _aliases in TOP_LEVEL_ALIASES.items():
    PREFIXED_TOP_LEVEL_COMMANDS[f"-{_command}"] = _command
    for _alias in _aliases:
        PREFIXED_TOP_LEVEL_COMMANDS[f"-{_alias}"] = _alias
PREFIXED_TOP_LEVEL_COMMANDS["-widget"] = "widget"


def _add_profile_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-P", "--profile", default="", help="Profile slug (default: current profile)")


def _print_scm_help() -> None:
    print("""\
scm — Snipcom terminal companion

DIRECT EXECUTION
  scm <name>              Find a command or text in your workflow by exact name
                          and run it. E.g. if you have "deploy-prod": scm deploy-prod
  scm <name> -ar <args>   Run workflow entry and append extra arguments.
  scm -ar <name> <args>   Same, flag-first form (equivalent).
  Example: if "list" contains "ls":  scm list -ar -l   →  runs: ls -l

INTERACTIVE NAVIGATOR  (scm  or  scm <query>)
  Opens a full-screen TUI with three sections:
    Heuristic/Deterministic  — context-aware and catalog suggestions
    AI recommendations       — synthetic commands from Ollama (type  nat <request>)
    Workflow                 — your personal commands and text files

  Navigation:
    Type            Filter candidates live
    Up / Down       Move between entries in the active section
    Left / Right    Switch between sections
    Enter           Execute the highlighted entry; or run buffer text if nothing is selected
    Tab             Load the highlighted entry into the input for editing, then Enter to run
    Shift+Tab       Accept the ghost suggestion shown in the input line
    Esc             Cancel edit / exit

  AI suggestions:
    In the navigator, type  nat <natural language request>  and the AI section
    will generate a synthetic command via Ollama. Example:
      nat find a file called something.txt
    Outside the navigator, use:
      scm -nat <request>         numbered picker with AI result included

OTHER COMMANDS
  scm -new               Create a new workflow text file (interactive)
  scm -cto               Copy terminal output to clipboard (pipe or tmux)
  scm -sto               Save terminal output to a workflow file (interactive)
  scm -find <query>      Search (aliases: -fd, -search)
  scm -f                 Favorites
  scm -w                 Workspace list
  scm -s <name>          Show entry details
  scm -x <name>          Send to linked terminal
  scm -src l             List import sources
  scm -shell install bash Install shell widget (Ctrl+G to open navigator from prompt)
  scm -help              Top-level help
  scm -<sub> -help       Help for any subcommand\
""")


def _split_direct_run_invocation(raw_argv: list[str]) -> tuple[str, list[str]] | None:
    if not raw_argv:
        return None
    first = str(raw_argv[0]).strip()
    if not first or first.startswith("-"):
        return None
    if len(raw_argv) == 1:
        return first, []
    marker_indexes = [index for index, item in enumerate(raw_argv[1:], start=1) if item in {"-arg", "-ar"}]
    if len(marker_indexes) != 1:
        return None
    marker_index = marker_indexes[0]
    return first, [str(item) for item in raw_argv[marker_index + 1 :]]


def _try_direct_run(name: str, *, extra_args: list[str] | None = None) -> int | None:
    try:
        ctx = _context("")
        entries = _workflow_entries(ctx)
        exact = [e for e in entries if e.display_name.casefold() == name.casefold()]
        if len(exact) != 1:
            return None
        entry = exact[0]
        command = _entry_text(ctx, entry).strip()
        if not command:
            return None
        extra_values = [str(item) for item in (extra_args or []) if str(item)]
        if extra_values:
            command = f"{command} {shlex.join(extra_values)}"
        _set_last_selection(ctx.profile_slug, entry.entry_id, entry.display_name)
        return int(subprocess.run(["bash", "-lc", command], check=False).returncode)
    except Exception:
        return None


def _try_direct_run_multiword(raw_argv: list[str]) -> int | None:
    """Try to run a workflow entry by name, supporting spaces in names.

    Handles: scm <name>  /  scm <multi word name>  /  scm <name> -arg <extra...>
    Tries longest name match first; falls through to nav if no exact match found.
    """
    if not raw_argv or str(raw_argv[0]).startswith("-"):
        return None
    try:
        ctx = _context("")
        entries = _workflow_entries(ctx)
        if not entries:
            return None

        # Find -arg/-ar marker (separates name tokens from extra args)
        marker_index: int | None = None
        for i, item in enumerate(raw_argv[1:], start=1):
            if str(item) in {"-arg", "-ar"}:
                marker_index = i
                break

        name_tokens = [str(t) for t in (raw_argv[:marker_index] if marker_index is not None else raw_argv)]
        extra_args = [str(t) for t in raw_argv[marker_index + 1:]] if marker_index is not None else []

        # Skip if any name token looks like a flag
        if any(t.startswith("-") for t in name_tokens):
            return None

        entry_by_name: dict[str, SnipcomEntry] = {e.display_name.casefold(): e for e in entries}

        # Try longest-first combinations of name_tokens as entry name
        for end in range(len(name_tokens), 0, -1):
            candidate_name = " ".join(name_tokens[:end])
            remaining = name_tokens[end:]

            # Remaining tokens only allowed when -arg marker is present
            if remaining and marker_index is None:
                continue

            matched_entry = entry_by_name.get(candidate_name.casefold())
            if matched_entry is None:
                continue

            command = _entry_text(ctx, matched_entry).strip()
            if not command:
                continue

            all_extra = remaining + extra_args
            if all_extra:
                command = f"{command} {shlex.join(all_extra)}"

            _set_last_selection(ctx.profile_slug, matched_entry.entry_id, matched_entry.display_name)
            return int(subprocess.run(["bash", "-lc", command], check=False).returncode)
    except Exception:
        return None
    return None


def _normalize_argv(argv: list[str]) -> list[str]:
    args = [str(item) for item in argv]
    if not args:
        return args
    normalized_args = ["--help" if item == "-help" else item for item in args]
    first = normalized_args[0]
    if first in {"--help", "-h"}:
        return ["--help", *normalized_args[1:]]
    mapped_command = PREFIXED_TOP_LEVEL_COMMANDS.get(first)
    if mapped_command is not None:
        return [mapped_command, *normalized_args[1:]]
    if first.startswith("--"):
        return normalized_args
    return ["nav", *normalized_args]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_launcher_program(),
        description="Snipcom terminal companion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Quick examples:\n"
            "  scm                           # interactive navigator\n"
            "  scm docker                    # navigator with initial query\n"
            "  scm -nav docker               # explicit navigator\n"
            "  scm -shell install bash       # editable prompt widget (Ctrl+G)\n"
            "  scm -find docker -n 10        # find\n"
            "  scm -f                        # favorites\n"
            "  scm -w                        # workspace\n"
            "  scm -pv --entry-id command:1  # preview one entry\n"
            "  scm -nat docker -n 10         # numbered picker + edit\n"
            "  scm -s .                      # show last selected\n"
            "  scm -x . -S linked-1          # send to linked terminal\n"
            "  scm -src l -j                 # list sources\n"
            "  scm -help                     # top-level help"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    nav_parser = subparsers.add_parser("nav", aliases=list(TOP_LEVEL_ALIASES["nav"]), help="Navi-like interactive terminal navigator")
    _add_profile_arg(nav_parser)
    nav_parser.add_argument("query", nargs="*", default=[], help="Optional initial search query")
    nav_parser.add_argument("-n", "--limit", type=int, default=30)
    nav_parser.add_argument("--preview-lines", type=int, default=DEFAULT_PREVIEW_LINES)
    nav_parser.add_argument("--no-context", action="store_true", help="Disable context-ranked suggestions")
    nav_parser.add_argument("--no-database", action="store_true", help="Disable catalog/database suggestions")
    nav_parser.set_defaults(handler=_handle_nav)

    find_parser = subparsers.add_parser("find", aliases=list(TOP_LEVEL_ALIASES["find"]), help="Search snippets and commands")
    _add_profile_arg(find_parser)
    find_parser.add_argument("query", nargs="*", default=[], help="Search query")
    find_parser.add_argument("-s", "--scope", choices=("all", "catalog", "workflow"), default="all")
    find_parser.add_argument("-n", "--limit", type=int, default=25)
    find_parser.add_argument("-j", "--json", action="store_true")
    find_parser.set_defaults(handler=_handle_find)

    favorites_parser = subparsers.add_parser("favorites", aliases=list(TOP_LEVEL_ALIASES["favorites"]), help="List favorites (commands and text snippets) from workspace")
    _add_profile_arg(favorites_parser)
    favorites_parser.add_argument("query", nargs="*", default=[], help="Optional text filter")
    favorites_parser.add_argument("-n", "--limit", type=int, default=50)
    favorites_parser.add_argument("-j", "--json", action="store_true")
    favorites_parser.set_defaults(handler=_handle_favorites)

    workspace_parser = subparsers.add_parser("workspace", aliases=list(TOP_LEVEL_ALIASES["workspace"]), help="List workspace commands and text snippets")
    _add_profile_arg(workspace_parser)
    workspace_parser.add_argument("query", nargs="*", default=[], help="Optional text filter")
    workspace_parser.add_argument("-n", "--limit", type=int, default=100)
    workspace_parser.add_argument("-j", "--json", action="store_true")
    workspace_parser.set_defaults(handler=_handle_workspace)

    preview_parser = subparsers.add_parser("preview", aliases=list(TOP_LEVEL_ALIASES["preview"]), help="Show command/text preview with metadata and methods")
    _add_profile_arg(preview_parser)
    preview_parser.add_argument("selector", nargs="?", default="", help="Entry selector (optional)")
    preview_parser.add_argument("--entry-id", default="", help="Exact entry id such as command:12 or file:path.txt")
    preview_parser.add_argument("--source-label", default="", help=argparse.SUPPRESS)
    preview_parser.add_argument("--reason", default="", help=argparse.SUPPRESS)
    preview_parser.add_argument("--lines", type=int, default=DEFAULT_PREVIEW_LINES, help="Maximum body lines to print")
    preview_parser.set_defaults(handler=_handle_preview)

    show_parser = subparsers.add_parser("show", aliases=list(TOP_LEVEL_ALIASES["show"]), help="Show command/snippet details")
    _add_profile_arg(show_parser)
    show_parser.add_argument("selector", help="Entry selector (command:id, id, '.', exact/fuzzy title)")
    show_parser.add_argument("-j", "--json", action="store_true")
    show_parser.set_defaults(handler=_handle_show)


    send_parser = subparsers.add_parser("send", aliases=list(TOP_LEVEL_ALIASES["send"]), help="Send a command/snippet to a linked terminal")
    _add_profile_arg(send_parser)
    send_parser.add_argument("selector")
    send_parser.add_argument("-S", "--session", default="", help="Linked terminal label")
    send_parser.add_argument("-y", "--yes-risk", action="store_true", help="Bypass interactive risk confirmation")
    send_parser.set_defaults(handler=_handle_send)

    history_parser = subparsers.add_parser("add-from-history", aliases=list(TOP_LEVEL_ALIASES["add-from-history"]), help="Create command snippets from shell history")
    _add_profile_arg(history_parser)
    history_parser.add_argument("-s", "--shell", choices=("bash", "zsh"), default="bash")
    history_parser.add_argument("-n", "--last", type=int, default=1)
    history_parser.add_argument("-t", "--title", default="")
    history_parser.add_argument("-f", "--family", default="history")
    history_parser.add_argument("-g", "--tags", default="")
    history_parser.add_argument("--dangerous", action="store_true")
    history_parser.set_defaults(handler=_handle_add_from_history)

    pick_parser = subparsers.add_parser("pick", aliases=list(TOP_LEVEL_ALIASES["pick"]), help="Interactive picker that prints selected command text")
    _add_profile_arg(pick_parser)
    pick_parser.add_argument("query", nargs="*", default=[])
    pick_parser.add_argument("-s", "--scope", choices=("all", "catalog", "workflow"), default="all")
    pick_parser.add_argument("-n", "--limit", type=int, default=25)
    pick_parser.add_argument("--no-preview", action="store_true", help="Disable interactive preview in picker")
    pick_parser.add_argument("--preview-lines", type=int, default=DEFAULT_PREVIEW_LINES, help="Maximum body lines shown in preview")
    pick_parser.set_defaults(handler=_handle_pick)

    nat_parser = subparsers.add_parser("nat", aliases=list(TOP_LEVEL_ALIASES["nat"]), help="Numbered picker that lets you edit selected command text")
    _add_profile_arg(nat_parser)
    nat_parser.add_argument("query", nargs="*", default=[])
    nat_parser.add_argument("-s", "--scope", choices=("all", "catalog", "workflow"), default="all")
    nat_parser.add_argument("-n", "--limit", type=int, default=25)
    nat_parser.add_argument("--no-preview", action="store_true", help="Disable interactive preview before selection")
    nat_parser.add_argument("--preview-lines", type=int, default=DEFAULT_PREVIEW_LINES, help="Maximum body lines shown in preview")
    nat_parser.set_defaults(handler=_handle_nat)

    shell_parser = subparsers.add_parser("shell", aliases=list(TOP_LEVEL_ALIASES["shell"]) + ["widget"], help="Shell widget helpers for editable prompt insertion")
    shell_subparsers = shell_parser.add_subparsers(dest="shell_command", required=True)
    shell_print = shell_subparsers.add_parser("print", aliases=["p"], help="Print shell integration snippet")
    shell_print.add_argument("shell", choices=("bash", "zsh", "fish"))
    shell_print.set_defaults(handler=_handle_shell_print)
    shell_install = shell_subparsers.add_parser("install", aliases=["i"], help="Install shell integration")
    shell_install.add_argument("shell", choices=("bash", "zsh", "fish"))
    shell_install.set_defaults(handler=_handle_shell_install)

    source_parser = subparsers.add_parser("source", aliases=list(TOP_LEVEL_ALIASES["source"]), help="Import source registry and refresh tools")
    source_subparsers = source_parser.add_subparsers(dest="source_command", required=True)

    source_add = source_subparsers.add_parser("add", aliases=["a"], help="Register or update an import source")
    _add_profile_arg(source_add)
    source_add.add_argument("-k", "--kind", choices=("navi-cheat", "cheatsheet", "json-pack"), required=True)
    source_add.add_argument("-N", "--name", default="")
    source_add.add_argument("-p", "--path", default="")
    source_add.add_argument("-g", "--git", default="")
    source_add.set_defaults(handler=_handle_source_add)

    source_list = source_subparsers.add_parser("list", aliases=["l", "ls"], help="List registered import sources")
    _add_profile_arg(source_list)
    source_list.add_argument("-j", "--json", action="store_true")
    source_list.set_defaults(handler=_handle_source_list)

    source_refresh = source_subparsers.add_parser("refresh", aliases=["r", "ref"], help="Refresh one source or all")
    _add_profile_arg(source_refresh)
    source_refresh.add_argument("target", help="Source id, name, or 'all'")
    source_refresh.set_defaults(handler=_handle_source_refresh)

    source_import_once = source_subparsers.add_parser("import-once", aliases=["i", "imp"], help="Import once from a path without registry")
    _add_profile_arg(source_import_once)
    source_import_once.add_argument("-k", "--kind", choices=("navi-cheat", "cheatsheet", "json-pack"), required=True)
    source_import_once.add_argument("-p", "--path", required=True)
    source_import_once.add_argument("-l", "--label", default="")
    source_import_once.set_defaults(handler=_handle_source_import_once)

    new_p = subparsers.add_parser("new", help="Create a new workflow text file interactively")
    _add_profile_arg(new_p)
    new_p.set_defaults(handler=_handle_new)

    cto_p = subparsers.add_parser("cto", help="Copy terminal output to clipboard")
    cto_p.set_defaults(handler=_handle_cto)

    sto_p = subparsers.add_parser("sto", help="Save terminal output to a workflow file")
    _add_profile_arg(sto_p)
    sto_p.set_defaults(handler=_handle_sto)

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if not raw_argv and _launcher_program() == "scm":
        raw_argv = ["-nav"]
    normalized_argv = _normalize_argv(raw_argv)

    # scm -help / --help / -h → custom human-readable help
    if raw_argv in (["-help"], ["--help"], ["-h"]):
        _print_scm_help()
        return 0

    # scm -ar <name> [args...] → flag-first argument syntax: find where name ends
    # (first flag-like token), rewrite as scm <name> -ar <args> and direct-run.
    if raw_argv and raw_argv[0] in ("-ar", "-arg"):
        rest = raw_argv[1:]
        pivot = next(
            (i for i, t in enumerate(rest) if str(t).startswith("-")),
            len(rest),
        )
        name_tokens = rest[:pivot]
        flag_args = rest[pivot:]
        if name_tokens:
            rewritten = list(name_tokens) + ["-ar"] + list(flag_args)
            result = _try_direct_run_multiword(rewritten)
            if result is not None:
                return result

    # scm <name> / scm <multi word name> / scm <name> -arg ... → direct workflow execution,
    # fall through to nav if no exact workflow name match found.
    if normalized_argv and normalized_argv[0] == "nav":
        result = _try_direct_run_multiword(raw_argv)
        if result is not None:
            return result

    parser = build_parser()
    if not normalized_argv:
        parser.print_help()
        return 1
    args = parser.parse_args(normalized_argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return int(handler(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
