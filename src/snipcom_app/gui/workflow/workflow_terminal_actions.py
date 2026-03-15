from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget

from ...integration.linked_terminal import (
    create_linked_terminal_session,
    linked_terminal_root_dir,
    linked_terminal_session_is_active,
    list_linked_terminal_sessions,
)
from ...core.repository import SnipcomEntry
from ...core.safety import evaluate_command_risk

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


def active_linked_terminal_sessions(window: "NoteCopyPaster") -> list[dict[str, object]]:
    return list_linked_terminal_sessions(linked_terminal_root_dir())


def selected_linked_terminal_label(window: "NoteCopyPaster") -> str:
    session = current_linked_terminal_session(window)
    if session is None:
        return ""
    return str(session.get("label", "") or "")


def record_command_usage(
    window: "NoteCopyPaster",
    entry: SnipcomEntry,
    *,
    event_kind: str,
    terminal_label: str = "",
    track_transition: bool = False,
    context: dict[str, object] | None = None,
) -> None:
    if not entry.is_command or entry.command_id is None:
        return
    try:
        window.repository.command_store.record_usage(
            entry.command_id,
            event_kind=event_kind,
            terminal_label=terminal_label,
            context=context,
            track_transition=track_transition,
        )
    except (OSError, ValueError):
        return


def current_linked_terminal_session(window: "NoteCopyPaster") -> dict[str, object] | None:
    sessions = active_linked_terminal_sessions(window)
    if not sessions:
        return None
    if window.current_linked_terminal_dir is not None:
        for session in sessions:
            if Path(session["runtime_dir"]) == window.current_linked_terminal_dir:
                return session
    session = sessions[0]
    window.current_linked_terminal_dir = Path(session["runtime_dir"])
    return session


def create_file_with_content(
    window: "NoteCopyPaster",
    file_name: str,
    content: str,
    *,
    open_after_create: bool = False,
) -> Path | None:
    file_name = file_name.strip()
    if not file_name:
        window.show_status("File creation canceled.")
        return None
    if "/" in file_name or file_name in {".", ".."}:
        QMessageBox.warning(window, "Invalid name", "Use a plain file name without folders.")
        return None

    path = window.repository.resolve_text_file_path(file_name, fallback_suffix=".txt")
    if path.exists():
        QMessageBox.warning(window, "File exists", f"{path.name} already exists.")
        return None

    try:
        path = window.repository.create_file(file_name, fallback_suffix=".txt")
        window.repository.write_text(path, content)
    except OSError as exc:
        QMessageBox.critical(window, "Create failed", str(exc))
        return None

    window.set_snip_type(path, "text_file")
    window.push_undo({"type": "create_file", "path": str(path)})
    window.refresh_table()
    if open_after_create:
        window.open_file(path)
    return path


def cancel_append_output_selection(window: "NoteCopyPaster") -> None:
    window.pending_append_output = None
    window.hide_instruction_banner()


def append_output_to_file(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    if window.pending_append_output is None:
        return
    entry = window.entry_for(target)
    if entry is None:
        return
    if entry.is_command:
        QMessageBox.warning(window, "Append failed", "Terminal output can only be appended into text files.")
        return
    label = str(window.pending_append_output["label"])
    output = str(window.pending_append_output["output"])
    current_content = window.read_file_text(entry, "Append failed")
    if current_content is None:
        return

    reply = QMessageBox.question(
        window,
        "Append output to file",
        f"Append the last output from {label} to {entry.display_name}?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return

    if not window.write_entry_text(entry, current_content + output, "Append failed"):
        return

    window.push_undo(
        {
            "type": "restore_entry_content",
            "entry_id": entry.entry_id,
            "previous_content": current_content,
            "message": f"Undid output append into {entry.display_name}.",
        }
    )
    cancel_append_output_selection(window)
    window.search_input.clear()
    window.refresh_table()
    window.show_status(f"Appended the last output into {entry.display_name}.")
    window.show_toast(f"Appended output into {entry.display_name}.")


def handle_send_command_button(
    window: "NoteCopyPaster",
    target: SnipcomEntry | Path | str,
    button: QWidget,
) -> None:
    entry = window.entry_for(target)
    if entry is None:
        return
    sessions = active_linked_terminal_sessions(window)
    if not sessions:
        send_file_content(window, entry, session=None)
        return

    menu = QMenu(button)
    for session in sessions:
        label = str(session["label"])
        action = window.configure_menu_action(
            QAction(label, menu),
            f"Send this command to {label}.",
        )
        action.triggered.connect(
            lambda _checked=False, session_dir=session["runtime_dir"], session_label=label: send_file_content(
                window,
                entry,
                session=session_dir,
                session_label=session_label,
            )
        )
        menu.addAction(action)

    menu.addSeparator()
    new_session_action = window.configure_menu_action(
        QAction("Open New Linked Terminal", menu),
        "Start a new linked terminal and send this command there.",
    )
    new_session_action.triggered.connect(lambda _checked=False: send_file_content(window, entry, session=None))
    menu.addAction(new_session_action)
    menu.exec(button.mapToGlobal(QPoint(0, button.height())))


def send_file_content(
    window: "NoteCopyPaster",
    target: SnipcomEntry | Path | str,
    session: Path | None = None,
    session_label: str | None = None,
) -> None:
    entry = window.entry_for(target)
    if entry is None:
        return
    command, _launch_options = window.build_command_text(entry, "Send failed")
    if command is None:
        return
    risk = evaluate_command_risk(command, dangerous_flag=bool(entry.dangerous))
    if risk.risky and not window.confirm_risky_command(
        action_label="send",
        entry_label=entry.display_name,
        command_text=command,
        reasons=risk.reasons,
    ):
        window.show_status(f"Canceled sending {entry.display_name}.")
        return

    if session is None:
        session_info = create_linked_terminal_session(linked_terminal_root_dir())
    else:
        session_info = {
            "runtime_dir": session,
            "label": session_label or session.name,
            "active": linked_terminal_session_is_active(session),
        }

    runtime_dir = session_info["runtime_dir"]
    session_label = str(session_info["label"])
    record_command_usage(
        window,
        entry,
        event_kind="send",
        terminal_label=session_label,
        track_transition=True,
        context={"runtime_dir": str(runtime_dir)},
    )
    window.observed_terminal_commands[str(runtime_dir)] = command
    delivery_ok, delivery = window.terminal_controller.dispatch_command_to_linked_terminal(
        runtime_dir,
        session_label,
        command,
    )
    if not delivery_ok:
        QMessageBox.warning(
            window,
            "Send failed",
            f"Could not start {session_label} for {entry.display_name}. The command was left queued.",
        )
        return
    if delivery == "restarted_and_queued":
        window.show_status(f"Started {session_label} and queued command from {entry.display_name}.")
        window.show_toast(f"Queued {entry.display_name} into {session_label}.")
        window.current_linked_terminal_dir = runtime_dir
        window.terminal_controller.refresh_linked_terminal_toolbar()
        return

    if delivery == "sent":
        window.show_status(f"Sent command from {entry.display_name} to {session_label}.")
        window.show_toast(f"Sent {entry.display_name} to {session_label}.")
        window.current_linked_terminal_dir = runtime_dir
        window.terminal_controller.refresh_linked_terminal_toolbar()
        return

    window.show_status(f"Queued command from {entry.display_name} for {session_label}.")
    window.show_toast(f"Queued {entry.display_name} for {session_label}.")
    window.current_linked_terminal_dir = runtime_dir
    window.terminal_controller.refresh_linked_terminal_toolbar()


def launch_file_content(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        return

    launch_options = window.launch_options_for(entry)
    if launch_options.get("use_linked_terminal", True) and not launch_options.get("copy_output_and_close", False):
        sessions = active_linked_terminal_sessions(window)
        current_dir = getattr(window, "current_linked_terminal_dir", None)
        session: Path | None = None
        if sessions:
            matching = [s for s in sessions if s["runtime_dir"] == current_dir]
            session = (matching[0] if matching else sessions[0])["runtime_dir"]  # type: ignore[assignment]
        send_file_content(window, entry, session=session)
        return

    command, launch_options = window.build_command_text(entry, "Launch failed")
    if command is None or launch_options is None:
        return
    risk = evaluate_command_risk(command, dangerous_flag=bool(entry.dangerous))
    if risk.risky and not window.confirm_risky_command(
        action_label="launch",
        entry_label=entry.display_name,
        command_text=command,
        reasons=risk.reasons,
    ):
        window.show_status(f"Canceled launch of {entry.display_name}.")
        return

    if launch_options["copy_output_and_close"]:
        record_command_usage(window, entry, event_kind="launch")
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            QMessageBox.critical(window, "Launch failed", str(exc))
            return

        combined_output = completed.stdout
        if completed.stderr:
            if combined_output and not combined_output.endswith("\n"):
                combined_output += "\n"
            combined_output += completed.stderr
        if combined_output:
            QApplication.clipboard().setText(combined_output)
            window.show_status(f"Copied command output from {entry.display_name}.")
            if completed.returncode == 0:
                window.show_toast(f"Copied command output from {entry.display_name}.")
            else:
                window.show_toast(
                    f"Copied output from {entry.display_name} with exit code {completed.returncode}."
                )
        else:
            window.show_status(f"{entry.display_name} produced no output.")
            if completed.returncode == 0:
                window.show_toast(f"{entry.display_name} produced no output.")
            else:
                window.show_toast(f"{entry.display_name} exited with code {completed.returncode} and no output.")
        return

    if not window.launch_in_terminal(command, bool(launch_options["keep_open"])):
        QMessageBox.warning(window, "Launch failed", f"Could not launch command from {entry.display_name}.")
        return

    record_command_usage(window, entry, event_kind="launch")
    window.show_feedback(f"Launched command from {entry.display_name}.")
