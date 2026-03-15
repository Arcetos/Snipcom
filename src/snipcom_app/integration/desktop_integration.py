from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtGui import QDesktopServices


def terminal_shell_command(command: str, keep_open: bool) -> str:
    if keep_open:
        return f"{command}; printf '\\n'; exec bash"
    return command


def build_terminal_command(executable: str, command: str, keep_open: bool) -> list[str] | None:
    terminal_name = Path(executable).name
    shell_command = terminal_shell_command(command, keep_open)

    if terminal_name == "xdg-terminal-exec":
        return [executable, "bash", "-lc", command]
    if terminal_name == "konsole":
        arguments = [executable]
        if keep_open:
            arguments.append("--noclose")
        arguments.extend(["-e", "bash", "-lc", command])
        return arguments
    if terminal_name in {"gnome-terminal", "ptyxis", "kgx"}:
        return [executable, "--", "bash", "-lc", shell_command]
    if terminal_name == "xterm":
        arguments = [executable]
        if keep_open:
            arguments.append("-hold")
        arguments.extend(["-e", "bash", "-lc", command])
        return arguments
    if terminal_name in {"kitty", "alacritty"}:
        if terminal_name == "kitty":
            return [executable, "bash", "-lc", shell_command]
        return [executable, "-e", "bash", "-lc", shell_command]
    if terminal_name == "xfce4-terminal":
        arguments = [executable]
        if keep_open:
            arguments.append("--hold")
        arguments.extend(["--command", f"bash -lc {shlex.quote(shell_command)}"])
        return arguments
    if terminal_name == "lxterminal":
        return [executable, "-e", f"bash -lc {shlex.quote(shell_command)}"]
    if terminal_name == "mate-terminal":
        return [executable, "-x", "bash", "-lc", shell_command]
    if terminal_name == "tilix":
        return [executable, "-e", "bash", "-lc", shell_command]
    if terminal_name == "terminator":
        return [executable, "-x", "bash", "-lc", shell_command]

    return [executable, "-e", "bash", "-lc", shell_command]


def candidate_terminal_executables(settings: dict[str, object], keep_open: bool) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        if not value:
            return
        executable = value.strip().split()[0]
        resolved = shutil.which(executable)
        if resolved is None and Path(executable).is_file():
            resolved = executable
        if not resolved or resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    add_candidate(str(settings.get("terminal_executable", "")))
    if not keep_open:
        add_candidate("xdg-terminal-exec")
    add_candidate(os.environ.get("TERMINAL"))

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").casefold()
    if "kde" in desktop:
        desktop_candidates = ["konsole"]
    elif any(name in desktop for name in {"gnome", "pop", "cosmic"}):
        desktop_candidates = ["ptyxis", "kgx", "gnome-terminal"]
    else:
        desktop_candidates = []
    for candidate in desktop_candidates + [
        "konsole",
        "ptyxis",
        "kgx",
        "gnome-terminal",
        "xfce4-terminal",
        "kitty",
        "alacritty",
        "mate-terminal",
        "tilix",
        "terminator",
        "lxterminal",
        "xterm",
    ]:
        add_candidate(candidate)

    return candidates


def launch_in_terminal(
    settings: dict[str, object],
    command: str,
    keep_open: bool,
    chooser: Callable[[], str | None],
) -> bool:
    for executable in candidate_terminal_executables(settings, keep_open):
        terminal_command = build_terminal_command(executable, command, keep_open)
        if terminal_command and QProcess.startDetached(terminal_command[0], terminal_command[1:]):
            return True

    selected_terminal = chooser()
    if selected_terminal:
        terminal_command = build_terminal_command(selected_terminal, command, keep_open)
        if terminal_command and QProcess.startDetached(terminal_command[0], terminal_command[1:]):
            return True

    return False


def opener_command(executable: str, path: Path) -> list[str]:
    opener_name = Path(executable).name
    if opener_name == "gio":
        return [executable, "open", str(path)]
    if opener_name in {"kioclient6", "kioclient", "kioclient5"}:
        return [executable, "exec", str(path)]
    return [executable, str(path)]


def candidate_opener_executables(settings: dict[str, object], setting_key: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add_candidate(value: str | None) -> None:
        if not value:
            return
        executable = value.strip().split()[0]
        resolved = shutil.which(executable)
        if resolved is None and Path(executable).is_file():
            resolved = executable
        if not resolved or resolved in seen:
            return
        seen.add(resolved)
        candidates.append(resolved)

    add_candidate(str(settings.get(setting_key, "")))
    desktop_hint = ":".join(
        value.casefold()
        for value in (
            os.environ.get("XDG_CURRENT_DESKTOP", ""),
            os.environ.get("DESKTOP_SESSION", ""),
        )
        if value
    )

    desktop_candidates: list[str] = []
    if any(name in desktop_hint for name in {"kde", "plasma"}):
        desktop_candidates.extend(["kioclient6", "kioclient", "kioclient5", "kde-open", "kde-open5"])
    elif any(name in desktop_hint for name in {"gnome", "pop", "cosmic", "unity", "cinnamon", "budgie", "mate"}):
        desktop_candidates.extend(["gio"])
    elif "xfce" in desktop_hint:
        desktop_candidates.extend(["exo-open", "gio"])
    elif any(name in desktop_hint for name in {"lxqt", "lubuntu"}):
        desktop_candidates.extend(["qtxdg-open", "gio"])
    elif any(name in desktop_hint for name in {"deepin", "dde"}):
        desktop_candidates.extend(["dde-open", "gio"])
    elif any(name in desktop_hint for name in {"enlightenment", ":e:"}):
        desktop_candidates.extend(["enlightenment_open"])

    for candidate in desktop_candidates + [
        "xdg-open",
        "gio",
        "kioclient6",
        "kioclient",
        "kioclient5",
        "kde-open",
        "kde-open5",
        "exo-open",
        "qtxdg-open",
        "dde-open",
        "enlightenment_open",
    ]:
        add_candidate(candidate)
    return candidates


def open_path_with_fallback(
    settings: dict[str, object],
    path: Path,
    setting_key: str,
    chooser: Callable[[], str | None],
) -> bool:
    if QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
        return True

    for executable in candidate_opener_executables(settings, setting_key):
        command = opener_command(executable, path)
        if QProcess.startDetached(command[0], command[1:]):
            return True

    selected_opener = chooser()
    if selected_opener:
        command = opener_command(selected_opener, path)
        if QProcess.startDetached(command[0], command[1:]):
            return True

    return False
