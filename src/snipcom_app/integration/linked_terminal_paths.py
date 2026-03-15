from __future__ import annotations

import os
from pathlib import Path

BACKEND_INTERACTIVE_TMUX = "interactive_tmux"
DEFAULT_LINKED_TERMINAL_BACKEND = BACKEND_INTERACTIVE_TMUX
TERMINAL_SUGGESTION_BINDING_DEFAULTS = {
    "suggestion_1": ["Alt+1", ""],
    "suggestion_2": ["Alt+2", ""],
    "suggestion_3": ["Alt+3", ""],
    "suggestion_4": ["Alt+4", ""],
    "suggestion_5": ["Alt+5", ""],
}
TERMINAL_SUGGESTION_COUNT = 5


def linked_terminal_root_dir() -> Path:
    runtime_root = Path(os.environ.get("XDG_RUNTIME_DIR") or (Path.home() / ".local" / "share" / "snipcom" / "runtime"))
    return runtime_root / "snipcom"


def linked_terminal_sessions_dir(root_dir: Path) -> Path:
    return root_dir / "linked-terminals"


def linked_terminal_meta_path(session_dir: Path) -> Path:
    return session_dir / "session.json"


def linked_terminal_last_output_path(session_dir: Path) -> Path:
    return session_dir / "last-output.txt"


def linked_terminal_last_command_path(session_dir: Path) -> Path:
    return session_dir / "last-command.txt"


def linked_terminal_pending_path(session_dir: Path) -> Path:
    return session_dir / "linked-terminal.pending"


def linked_terminal_processing_path(session_dir: Path) -> Path:
    return session_dir / "linked-terminal.processing"


def linked_terminal_payloads_dir(session_dir: Path) -> Path:
    return session_dir / "payloads"


def linked_terminal_bashrc_path(session_dir: Path) -> Path:
    return session_dir / "interactive-shell.bashrc"


def linked_terminal_command_log_path(session_dir: Path) -> Path:
    return session_dir / "command-log.tsv"


def linked_terminal_last_cwd_path(session_dir: Path) -> Path:
    return session_dir / "last-cwd.txt"


def read_linked_terminal_last_cwd(session_dir: Path) -> str:
    try:
        return linked_terminal_last_cwd_path(session_dir).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def linked_terminal_ai_request_path(session_dir: Path) -> Path:
    return session_dir / "ai-request.txt"


def linked_terminal_ai_suggestion_path(session_dir: Path, index: int) -> Path:
    safe_index = max(1, min(TERMINAL_SUGGESTION_COUNT, int(index)))
    return session_dir / f"ai-suggestion-{safe_index}.txt"
