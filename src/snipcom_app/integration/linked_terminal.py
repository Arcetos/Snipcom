from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .desktop_integration import build_terminal_command, candidate_terminal_executables
from .linked_terminal_paths import (
    BACKEND_INTERACTIVE_TMUX,
    DEFAULT_LINKED_TERMINAL_BACKEND,
    TERMINAL_SUGGESTION_BINDING_DEFAULTS,
    TERMINAL_SUGGESTION_COUNT,
    linked_terminal_root_dir,
    linked_terminal_sessions_dir,
    linked_terminal_meta_path,
    linked_terminal_last_output_path,
    linked_terminal_last_command_path,
    linked_terminal_pending_path,
    linked_terminal_processing_path,
    linked_terminal_payloads_dir,
    linked_terminal_bashrc_path,
    linked_terminal_command_log_path,
    linked_terminal_last_cwd_path,
    read_linked_terminal_last_cwd,
    linked_terminal_ai_request_path,
    linked_terminal_ai_suggestion_path,
)
from .linked_terminal_backend import (
    _tmux_executable,
    _pid_is_alive,
    _tmux_has_session,
    _tmux_attached_client_count,
    _tmux_kill_session,
    _tmux_target,
    _tmux_run,
    _apply_tmux_suggestion_bindings,
)

# Re-export path helpers and constants so callers that import from this module
# continue to work without changes.
__all__ = [
    "BACKEND_INTERACTIVE_TMUX",
    "DEFAULT_LINKED_TERMINAL_BACKEND",
    "TERMINAL_SUGGESTION_BINDING_DEFAULTS",
    "TERMINAL_SUGGESTION_COUNT",
    "linked_terminal_root_dir",
    "linked_terminal_sessions_dir",
    "linked_terminal_meta_path",
    "linked_terminal_last_output_path",
    "linked_terminal_last_command_path",
    "linked_terminal_pending_path",
    "linked_terminal_processing_path",
    "linked_terminal_payloads_dir",
    "linked_terminal_bashrc_path",
    "linked_terminal_command_log_path",
    "linked_terminal_last_cwd_path",
    "read_linked_terminal_last_cwd",
    "linked_terminal_ai_request_path",
    "linked_terminal_ai_suggestion_path",
    "linked_terminal_session_is_active",
    "load_linked_terminal_session",
    "save_linked_terminal_session",
    "list_linked_terminal_sessions",
    "create_linked_terminal_session",
    "dispatch_linked_terminal_command",
    "launch_linked_terminal_session",
    "read_linked_terminal_current_input",
    "read_linked_terminal_last_output",
    "clear_linked_terminal_ai_suggestions",
    "write_linked_terminal_ai_suggestions",
    "refresh_interactive_linked_terminal_bindings",
    "close_linked_terminal_session",
    "close_all_linked_terminal_sessions",
]


def _interactive_session_is_active(session_dir: Path) -> bool:
    try:
        data = json.loads(linked_terminal_meta_path(session_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    tmux_session = str(data.get("tmux_session", "") or "")
    terminal_pid = int(data.get("terminal_pid", 0) or 0)
    attached_client_count = _tmux_attached_client_count(tmux_session)
    if attached_client_count is None:
        return False
    if terminal_pid > 0 and not _pid_is_alive(terminal_pid):
        _tmux_kill_session(tmux_session)
        return False
    if attached_client_count > 0:
        return True
    launched_at = str(data.get("launched_at", "") or "").strip()
    if terminal_pid > 0 and _pid_is_alive(terminal_pid) and launched_at:
        try:
            launched_at_dt = datetime.fromisoformat(launched_at)
        except ValueError:
            launched_at_dt = None
        if launched_at_dt is not None:
            if launched_at_dt.tzinfo is None:
                launched_at_dt = launched_at_dt.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - launched_at_dt).total_seconds() < 3.0:
                return True
    _tmux_kill_session(tmux_session)
    return False


def linked_terminal_session_is_active(session_dir: Path) -> bool:
    return _interactive_session_is_active(session_dir)


def load_linked_terminal_session(session_dir: Path) -> dict[str, object] | None:
    meta_path = linked_terminal_meta_path(session_dir)
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    session_id = str(data.get("id", session_dir.name)).strip() or session_dir.name
    label = str(data.get("label", session_id)).strip() or session_id
    sequence = int(data.get("sequence", 0) or 0)
    terminal_pid = int(data.get("terminal_pid", 0) or 0)
    created_at = str(data.get("created_at", "")).strip()
    launched_at = str(data.get("launched_at", "")).strip()
    tmux_session = str(data.get("tmux_session", "")).strip()
    return {
        "id": session_id,
        "label": label,
        "sequence": sequence,
        "terminal_pid": terminal_pid,
        "created_at": created_at,
        "launched_at": launched_at,
        "tmux_session": tmux_session,
        "runtime_dir": session_dir,
        "active": _interactive_session_is_active(session_dir),
    }


def save_linked_terminal_session(session_dir: Path, session: dict[str, object]) -> None:
    linked_terminal_meta_path(session_dir).write_text(
        json.dumps(
            {
                "id": session["id"],
                "label": session["label"],
                "sequence": session["sequence"],
                "terminal_pid": int(session.get("terminal_pid", 0) or 0),
                "created_at": session["created_at"],
                "launched_at": str(session.get("launched_at", "")),
                "tmux_session": str(session.get("tmux_session", "")),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def list_linked_terminal_sessions(root_dir: Path, *, active_only: bool = True) -> list[dict[str, object]]:
    sessions_dir = linked_terminal_sessions_dir(root_dir)
    if not sessions_dir.exists():
        return []

    sessions: list[dict[str, object]] = []
    for session_dir in sessions_dir.iterdir():
        if not session_dir.is_dir():
            continue
        session = load_linked_terminal_session(session_dir)
        if not session:
            continue
        if active_only and not bool(session["active"]):
            continue
        sessions.append(session)

    sessions.sort(key=lambda item: (int(item.get("sequence", 0)), str(item.get("created_at", "")), str(item.get("label", ""))))
    return sessions


def create_linked_terminal_session(root_dir: Path) -> dict[str, object]:
    root_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = linked_terminal_sessions_dir(root_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)

    existing_sessions = list_linked_terminal_sessions(root_dir, active_only=True)
    next_sequence = max((int(session.get("sequence", 0)) for session in existing_sessions), default=0) + 1
    session_id = uuid.uuid4().hex
    session_dir = sessions_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    session = {
        "id": session_id,
        "label": f"Linked Terminal {next_sequence}",
        "sequence": next_sequence,
        "terminal_pid": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "launched_at": "",
        "tmux_session": f"snipcom_{session_id[:12]}",
        "runtime_dir": session_dir,
        "active": False,
    }
    save_linked_terminal_session(session_dir, session)
    return session


def _queue_payload(session_dir: Path, command: str) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    payload_dir = linked_terminal_payloads_dir(session_dir)
    payload_dir.mkdir(parents=True, exist_ok=True)
    payload_path = payload_dir / f"{uuid.uuid4().hex}.command"
    payload_path.write_text(command, encoding="utf-8")
    with linked_terminal_pending_path(session_dir).open("a", encoding="utf-8") as pending_file:
        pending_file.write(f"{payload_path}\n")


def _tmux_send_command(tmux_session: str, command: str) -> None:
    executable = _tmux_executable()
    if not executable:
        raise OSError("tmux is not installed.")
    buffer_name = f"snipcom-{uuid.uuid4().hex}"
    subprocess.run(
        [executable, "load-buffer", "-b", buffer_name, "-"],
        input=command,
        text=True,
        check=True,
    )
    try:
        subprocess.run([executable, "paste-buffer", "-d", "-b", buffer_name, "-t", _tmux_target(tmux_session)], check=True)
    finally:
        subprocess.run([executable, "delete-buffer", "-b", buffer_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    subprocess.run([executable, "send-keys", "-t", _tmux_target(tmux_session), "C-m"], check=True)


def dispatch_linked_terminal_command(session_dir: Path, command: str) -> str:
    session = load_linked_terminal_session(session_dir)
    if session and _interactive_session_is_active(session_dir):
        _tmux_send_command(str(session.get("tmux_session", "")), command)
        return "sent"
    _queue_payload(session_dir, command)
    return "queued"


def _interactive_shell_rc_content(
    *,
    last_command_path: str,
    command_log_path: str,
    cwd_path: str,
    ai_request_path: str,
    ai_suggestion_1_path: str,
) -> str:
    return f"""for __snipcom_sysrc in /etc/bashrc /etc/bash.bashrc /etc/bash/bashrc; do
  [ -f "$__snipcom_sysrc" ] && {{ source "$__snipcom_sysrc"; break; }}
done
unset __snipcom_sysrc
if [ -f "$HOME/.bashrc" ]; then
  source "$HOME/.bashrc"
fi

SNIPCOM_LAST_COMMAND_FILE={last_command_path}
SNIPCOM_COMMAND_LOG_FILE={command_log_path}
SNIPCOM_CWD_FILE={cwd_path}
SNIPCOM_AI_REQUEST_FILE={ai_request_path}
SNIPCOM_AI_SUGGESTION_1_FILE={ai_suggestion_1_path}
__snipcom_inside_hook=0
__snipcom_last_command=""

__snipcom_preexec() {{
  [ "${{__snipcom_inside_hook:-0}}" -eq 1 ] && return
  local cmd="$BASH_COMMAND"
  case "$cmd" in
    __snipcom_* )
      return
      ;;
    "history -a"|"builtin history -a" )
      return
      ;;
  esac
  __snipcom_last_command="$cmd"
}}

__snipcom_precmd() {{
  __snipcom_inside_hook=1
  builtin history -a
  printf '%s\\n' "$PWD" > "$SNIPCOM_CWD_FILE"
  if [ -n "$__snipcom_last_command" ]; then
    printf '%s\\n' "$__snipcom_last_command" > "$SNIPCOM_LAST_COMMAND_FILE"
    printf '%s\\t%s\\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$__snipcom_last_command" >> "$SNIPCOM_COMMAND_LOG_FILE"
  fi
  __snipcom_inside_hook=0
}}

trap '__snipcom_preexec' DEBUG
if [ -n "${{PROMPT_COMMAND:-}}" ]; then
  PROMPT_COMMAND="__snipcom_precmd;$PROMPT_COMMAND"
else
  PROMPT_COMMAND="__snipcom_precmd"
fi

nat() {{
  local request="$*"
  local saved_request=""
  local suggestion=""
  if [ -f "$SNIPCOM_AI_REQUEST_FILE" ]; then
    saved_request="$(cat -- "$SNIPCOM_AI_REQUEST_FILE" 2>/dev/null)"
  fi
  if [ -f "$SNIPCOM_AI_SUGGESTION_1_FILE" ]; then
    suggestion="$(cat -- "$SNIPCOM_AI_SUGGESTION_1_FILE" 2>/dev/null)"
  fi
  if [ -n "$request" ] && [ -n "$suggestion" ] && [ "$request" = "$saved_request" ]; then
    printf 'AI suggestion is ready. Use Alt+1 to insert it if Enter replacement did not trigger.\\n' >&2
    return 130
  fi
  printf 'No AI suggestion is ready for: nat %s\\n' "$request" >&2
  return 127
}}
"""


def _write_interactive_shell_rc(session_dir: Path) -> Path:
    rcfile = linked_terminal_bashrc_path(session_dir)
    rcfile.write_text(
        _interactive_shell_rc_content(
            last_command_path=shlex.quote(str(linked_terminal_last_command_path(session_dir))),
            command_log_path=shlex.quote(str(linked_terminal_command_log_path(session_dir))),
            cwd_path=shlex.quote(str(linked_terminal_last_cwd_path(session_dir))),
            ai_request_path=shlex.quote(str(linked_terminal_ai_request_path(session_dir))),
            ai_suggestion_1_path=shlex.quote(str(linked_terminal_ai_suggestion_path(session_dir, 1))),
        ),
        encoding="utf-8",
    )
    return rcfile


def _interactive_ensure_tmux_session(session_dir: Path, session: dict[str, object], settings: dict[str, object] | None = None) -> None:
    tmux_session = str(session.get("tmux_session", "") or "")
    if not tmux_session:
        raise OSError("Interactive linked terminal is missing its tmux session name.")
    if _tmux_has_session(tmux_session):
        return
    executable = _tmux_executable()
    if not executable:
        raise OSError("tmux is not installed.")

    rcfile = _write_interactive_shell_rc(session_dir)
    linked_terminal_last_command_path(session_dir).touch(exist_ok=True)
    linked_terminal_command_log_path(session_dir).touch(exist_ok=True)
    linked_terminal_last_cwd_path(session_dir).touch(exist_ok=True)
    linked_terminal_last_output_path(session_dir).touch(exist_ok=True)
    linked_terminal_ai_request_path(session_dir).write_text("", encoding="utf-8")
    for index in range(1, TERMINAL_SUGGESTION_COUNT + 1):
        linked_terminal_ai_suggestion_path(session_dir, index).write_text("", encoding="utf-8")
    command = ["bash", "--rcfile", str(rcfile), "-i"]
    subprocess.run([executable, "new-session", "-d", "-s", tmux_session, *command], check=True)
    subprocess.run([executable, "set-option", "-t", tmux_session, "history-limit", "5000"], check=False)
    _apply_tmux_suggestion_bindings(session_dir, tmux_session, settings or {})


def _interactive_flush_pending_commands(session_dir: Path, session: dict[str, object]) -> None:
    pending_path = linked_terminal_pending_path(session_dir)
    processing_path = linked_terminal_processing_path(session_dir)
    if not pending_path.exists() or pending_path.stat().st_size == 0:
        return
    pending_path.replace(processing_path)
    tmux_session = str(session.get("tmux_session", "") or "")
    try:
        with processing_path.open("r", encoding="utf-8") as pending_file:
            for payload_line in pending_file:
                payload_path = Path(payload_line.strip())
                if not payload_path.exists():
                    continue
                try:
                    command = payload_path.read_text(encoding="utf-8")
                except OSError:
                    payload_path.unlink(missing_ok=True)
                    continue
                payload_path.unlink(missing_ok=True)
                if command.strip():
                    _tmux_send_command(tmux_session, command)
    finally:
        processing_path.unlink(missing_ok=True)


def _launch_terminal_process(executable: str, command: str) -> subprocess.Popen[bytes] | None:
    terminal_command = build_terminal_command(executable, command, False)
    if not terminal_command:
        return None
    try:
        return subprocess.Popen(terminal_command, start_new_session=True)
    except OSError:
        return None


def launch_linked_terminal_session(
    settings: dict[str, object],
    session_dir: Path,
    label: str,
    chooser,
) -> bool:
    session = load_linked_terminal_session(session_dir)
    if session is None:
        return False
    try:
        _interactive_ensure_tmux_session(session_dir, session, settings)
    except (OSError, subprocess.CalledProcessError):
        return False

    tmux_session = str(session.get("tmux_session", "") or "")
    shell_command = f"tmux attach-session -t {shlex.quote(tmux_session)}"

    def try_launch(executable: str) -> bool:
        process = _launch_terminal_process(executable, shell_command)
        if process is None:
            return False
        session["terminal_pid"] = process.pid
        session["launched_at"] = datetime.now(timezone.utc).isoformat()
        save_linked_terminal_session(session_dir, session)
        try:
            _interactive_flush_pending_commands(session_dir, session)
        except (OSError, subprocess.CalledProcessError):
            pass
        return True

    for executable in candidate_terminal_executables(settings, False):
        if try_launch(executable):
            return True

    selected_terminal = chooser()
    if selected_terminal and try_launch(selected_terminal):
        return True
    return False


def _interactive_read_output(session_dir: Path) -> str:
    session = load_linked_terminal_session(session_dir)
    if not session:
        raise FileNotFoundError(session_dir)
    tmux_session = str(session.get("tmux_session", "") or "")
    executable = _tmux_executable()
    if not executable or not _tmux_has_session(tmux_session):
        return linked_terminal_last_output_path(session_dir).read_text(encoding="utf-8")
    output = subprocess.check_output(
        [executable, "capture-pane", "-p", "-J", "-S", "-200", "-t", _tmux_target(tmux_session)],
        text=True,
    )
    linked_terminal_last_output_path(session_dir).write_text(output, encoding="utf-8")
    return output


def read_linked_terminal_current_input(session_dir: Path) -> str:
    session = load_linked_terminal_session(session_dir)
    if not session:
        return ""
    tmux_session = str(session.get("tmux_session", "") or "")
    executable = _tmux_executable()
    if not executable or not _tmux_has_session(tmux_session):
        return ""
    try:
        output = subprocess.check_output(
            [executable, "capture-pane", "-p", "-J", "-S", "-8", "-t", _tmux_target(tmux_session)],
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    current_line = lines[-1].strip()
    if not current_line:
        return ""
    match = re.search(r"[#$>%]\s+nat\s+(.+)$", current_line)
    if match:
        return f"nat {match.group(1).strip()}"
    if current_line.casefold().startswith("nat "):
        return current_line.strip()
    match = re.search(r"[#$>%]\s+(.+)$", current_line)
    if match:
        return match.group(1).strip()
    match = re.search(r"\bnat\s+(.+)$", current_line)
    if match:
        return f"nat {match.group(1).strip()}"
    return ""


def clear_linked_terminal_ai_suggestions(session_dir: Path) -> None:
    linked_terminal_ai_request_path(session_dir).write_text("", encoding="utf-8")
    for index in range(1, TERMINAL_SUGGESTION_COUNT + 1):
        linked_terminal_ai_suggestion_path(session_dir, index).write_text("", encoding="utf-8")


def write_linked_terminal_ai_suggestions(session_dir: Path, request_text: str, suggestions: list[str]) -> None:
    linked_terminal_ai_request_path(session_dir).write_text(request_text.strip(), encoding="utf-8")
    for index in (1, 2, 3):
        suggestion = suggestions[index - 1].strip() if index - 1 < len(suggestions) else ""
        linked_terminal_ai_suggestion_path(session_dir, index).write_text(suggestion, encoding="utf-8")


def refresh_interactive_linked_terminal_bindings(root_dir: Path, settings: dict[str, object]) -> None:
    for session in list_linked_terminal_sessions(root_dir, active_only=True):
        tmux_session = str(session.get("tmux_session", "") or "")
        session_dir = Path(session["runtime_dir"])
        if tmux_session:
            _apply_tmux_suggestion_bindings(session_dir, tmux_session, settings)


def read_linked_terminal_last_output(session_dir: Path) -> str:
    return _interactive_read_output(session_dir)


def _close_interactive_linked_terminal_session(session_dir: Path, session: dict[str, object]) -> None:
    tmux_session = str(session.get("tmux_session", "") or "")
    _tmux_kill_session(tmux_session)
    terminal_pid = int(session.get("terminal_pid", 0) or 0)
    if terminal_pid > 0:
        try:
            os.killpg(terminal_pid, signal.SIGTERM)
        except OSError:
            pass
        time.sleep(0.1)
        try:
            os.killpg(terminal_pid, signal.SIGKILL)
        except OSError:
            pass


def close_linked_terminal_session(session_dir: Path) -> None:
    session = load_linked_terminal_session(session_dir)
    if not session:
        return
    _close_interactive_linked_terminal_session(session_dir, session)


def close_all_linked_terminal_sessions(root_dir: Path) -> None:
    for session in list_linked_terminal_sessions(root_dir, active_only=True):
        close_linked_terminal_session(Path(session["runtime_dir"]))
