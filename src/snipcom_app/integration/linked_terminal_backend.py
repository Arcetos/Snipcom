from __future__ import annotations

import shlex
import shutil
import subprocess
import os
from pathlib import Path

from ..core.helpers import normalize_binding_sequences
from .linked_terminal_paths import (
    TERMINAL_SUGGESTION_COUNT,
    TERMINAL_SUGGESTION_BINDING_DEFAULTS,
    linked_terminal_ai_request_path,
    linked_terminal_ai_suggestion_path,
)


def _tmux_executable() -> str | None:
    return shutil.which("tmux")


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _tmux_has_session(tmux_session: str) -> bool:
    executable = _tmux_executable()
    if not executable or not tmux_session.strip():
        return False
    result = subprocess.run(
        [executable, "has-session", "-t", tmux_session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _tmux_attached_client_count(tmux_session: str) -> int | None:
    executable = _tmux_executable()
    if not executable or not tmux_session.strip():
        return None
    try:
        output = subprocess.check_output(
            [executable, "display-message", "-p", "-t", tmux_session, "#{session_attached}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return max(0, int(output))
    except ValueError:
        return None


def _tmux_kill_session(tmux_session: str) -> None:
    executable = _tmux_executable()
    if not executable or not tmux_session.strip():
        return
    subprocess.run(
        [executable, "kill-session", "-t", tmux_session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _tmux_target(tmux_session: str) -> str:
    return f"{tmux_session}:0.0"


def _settings_terminal_suggestion_bindings(settings: dict[str, object]) -> dict[str, list[str]]:
    return normalize_binding_sequences(
        settings.get("terminal_suggestion_bindings", {}),
        TERMINAL_SUGGESTION_BINDING_DEFAULTS,
        slot_count=2,
    )


def _portable_binding_to_tmux(binding: str) -> str:
    cleaned = binding.strip().casefold()
    mapping = {
        "alt+1": "M-1",
        "alt+2": "M-2",
        "alt+3": "M-3",
        "alt+4": "M-4",
        "alt+5": "M-5",
    }
    return mapping.get(cleaned, "")


def _tmux_run(executable: str, *args: str, quiet: bool = False) -> None:
    kwargs: dict[str, object] = {"check": False}
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    subprocess.run([executable, *args], **kwargs)


def _configure_tmux_session_base(executable: str, tmux_session: str) -> None:
    _tmux_run(executable, "set-option", "-t", tmux_session, "xterm-keys", "on")
    _tmux_run(executable, "set-option", "-t", tmux_session, "extended-keys", "on")
    _tmux_run(
        executable,
        "set-hook",
        "-t",
        tmux_session,
        "client-detached",
        f'run-shell "sleep 0.2; {shlex.quote(executable)} list-clients -t {shlex.quote(tmux_session)} >/dev/null 2>&1 || {shlex.quote(executable)} kill-session -t {shlex.quote(tmux_session)} >/dev/null 2>&1"',
    )


def _set_tmux_suggestion_paths(executable: str, session_dir: Path, tmux_session: str) -> None:
    _tmux_run(executable, "set-option", "-t", tmux_session, "@snipcom_ai_request", str(linked_terminal_ai_request_path(session_dir)))
    for index in range(1, TERMINAL_SUGGESTION_COUNT + 1):
        _tmux_run(
            executable,
            "set-option",
            "-t",
            tmux_session,
            f"@snipcom_suggestion_{index}",
            str(linked_terminal_ai_suggestion_path(session_dir, index)),
        )


def _bind_tmux_suggestion_keys(executable: str, tmux_session: str, settings: dict[str, object]) -> None:
    suggestion_bindings = _settings_terminal_suggestion_bindings(settings)
    for action_name, bindings in suggestion_bindings.items():
        suggestion_index = int(action_name.rsplit("_", 1)[-1])
        option_name = f"@snipcom_suggestion_{suggestion_index}"
        for binding in bindings:
            tmux_key = _portable_binding_to_tmux(binding)
            if not tmux_key:
                continue
            _tmux_run(executable, "unbind-key", "-n", tmux_key, quiet=True)
            _tmux_run(
                executable,
                "bind-key",
                "-n",
                tmux_key,
                "run-shell",
                f'file="#{{{option_name}}}"; [ -s "$file" ] || exit 0; tmux send-keys -t "#{{pane_id}}" C-u; tmux load-buffer -b snipcom-inline "$file"; tmux paste-buffer -d -b snipcom-inline -t "#{{pane_id}}"',
            )


def _bind_tmux_enter_passthrough(executable: str) -> None:
    enter_handler = (
        'capture="$(tmux capture-pane -p -J -S -8 -t "#{pane_id}")"; '
        'current_line="$(printf \'%s\\n\' "$capture" | awk \'NF { line=$0 } END { print line }\')"; '
        'request_file="#{@snipcom_ai_request}"; '
        'suggestion_file="#{@snipcom_suggestion_1}"; '
        'typed="$(printf \'%s\\n\' "$current_line" | sed -n \'s/.*nat[[:space:]]\\+//p\' | tail -n 1)"; '
        'request="$(cat -- "$request_file" 2>/dev/null)"; '
        'if [ -n "$typed" ] && [ -s "$suggestion_file" ] && [ "$typed" = "$request" ]; then '
        'tmux send-keys -t "#{pane_id}" C-u; '
        'tmux load-buffer -b snipcom-inline "$suggestion_file"; '
        'tmux paste-buffer -d -b snipcom-inline -t "#{pane_id}"; '
        'else tmux send-keys -t "#{pane_id}" C-m; fi'
    )
    for enter_key in ("Enter", "C-m", "KPEnter"):
        _tmux_run(executable, "unbind-key", "-n", enter_key, quiet=True)
        _tmux_run(executable, "bind-key", "-n", enter_key, "run-shell", enter_handler)


def _apply_tmux_suggestion_bindings(session_dir: Path, tmux_session: str, settings: dict[str, object]) -> None:
    executable = _tmux_executable()
    if not executable:
        return
    _configure_tmux_session_base(executable, tmux_session)
    _set_tmux_suggestion_paths(executable, session_dir, tmux_session)
    _bind_tmux_suggestion_keys(executable, tmux_session, settings)
    _bind_tmux_enter_passthrough(executable)
