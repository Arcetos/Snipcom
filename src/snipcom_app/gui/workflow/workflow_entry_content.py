from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QRadioButton,
    QVBoxLayout,
)

from ...core.repository import SnipcomEntry

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


def edit_launch_options(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return

    current_options = window.launch_options_for(entry)

    dialog = QDialog(window)
    dialog.setWindowTitle("Launch Options")
    dialog.resize(380, 280)

    layout = QVBoxLayout(dialog)

    linked_group = QGroupBox("Terminal routing")
    linked_layout = QVBoxLayout()
    linked_terminal_checkbox = QCheckBox("Use linked terminal (sends command to linked terminal window)")
    linked_terminal_checkbox.setChecked(bool(current_options.get("use_linked_terminal", True)))
    linked_layout.addWidget(linked_terminal_checkbox)
    linked_group.setLayout(linked_layout)
    layout.addWidget(linked_group)

    terminal_group = QGroupBox("Terminal behavior")
    terminal_layout = QVBoxLayout()
    keep_open_radio = QRadioButton("Keep terminal open after launch")
    close_after_radio = QRadioButton("Close terminal after launch")
    radio_group = QButtonGroup(dialog)
    radio_group.setExclusive(True)
    radio_group.addButton(keep_open_radio)
    radio_group.addButton(close_after_radio)
    if current_options["keep_open"]:
        keep_open_radio.setChecked(True)
    else:
        close_after_radio.setChecked(True)
    terminal_layout.addWidget(keep_open_radio)
    terminal_layout.addWidget(close_after_radio)
    terminal_group.setLayout(terminal_layout)
    layout.addWidget(terminal_group)

    extra_group = QGroupBox("Extra launch behavior")
    extra_layout = QVBoxLayout()
    ask_arguments_checkbox = QCheckBox("Ask for extra arguments on launch")
    ask_arguments_checkbox.setChecked(bool(current_options["ask_extra_arguments"]))
    copy_output_checkbox = QCheckBox("Run command, copy output, close terminal")
    copy_output_checkbox.setChecked(bool(current_options["copy_output_and_close"]))
    extra_layout.addWidget(ask_arguments_checkbox)
    extra_layout.addWidget(copy_output_checkbox)
    extra_group.setLayout(extra_layout)
    layout.addWidget(extra_group)

    def update_terminal_controls() -> None:
        use_linked = linked_terminal_checkbox.isChecked()
        copy_output = copy_output_checkbox.isChecked()
        terminal_group.setEnabled(not use_linked and not copy_output)
        copy_output_checkbox.setEnabled(not use_linked)

    linked_terminal_checkbox.toggled.connect(update_terminal_controls)
    copy_output_checkbox.toggled.connect(update_terminal_controls)
    update_terminal_controls()

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    window.set_launch_options(
        entry,
        keep_open=keep_open_radio.isChecked(),
        ask_extra_arguments=ask_arguments_checkbox.isChecked(),
        copy_output_and_close=copy_output_checkbox.isChecked(),
        use_linked_terminal=linked_terminal_checkbox.isChecked(),
    )
    window.show_feedback(f"Updated launch options for {entry.display_name}.")


def open_command_editor(window: "NoteCopyPaster", entry: SnipcomEntry) -> None:
    if not entry.is_command or entry.command_id is None:
        return
    try:
        record = window.repository.command_store.get_command(entry.command_id)
    except KeyError:
        window.refresh_table()
        QMessageBox.warning(window, "Missing command", f"{entry.display_name} no longer exists.")
        return

    dialog = QDialog(window)
    dialog.setWindowTitle(record.title)
    dialog.resize(640, 420)

    layout = QVBoxLayout(dialog)
    help_label = QLabel("Edit the command content. Save writes it back into the command store.")
    help_label.setWordWrap(True)
    layout.addWidget(help_label)

    editor = QPlainTextEdit(record.body)
    layout.addWidget(editor, 1)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)
    editor.setFocus()

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    new_content = editor.toPlainText()
    if new_content == record.body:
        return

    window.repository.command_store.update_command(record.command_id, body=new_content)
    window.push_undo(
        {
            "type": "restore_entry_content",
            "entry_id": entry.entry_id,
            "previous_content": record.body,
            "message": f"Undid the content edit for {entry.display_name}.",
        }
    )
    window.refresh_table()
    window.show_status(f"Saved {entry.display_name}.")


def open_file(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return

    if entry.is_folder:
        window.open_folder_entry(entry)
        return

    if entry.is_command:
        window.record_command_usage(entry, event_kind="open")
        open_command_editor(window, entry)
        return

    assert entry.path is not None
    if not window.open_path_with_fallback(
        entry.path,
        "file_opener_executable",
        "Choose file opener",
        "Open failed",
    ):
        QMessageBox.warning(window, "Open failed", f"Could not open {entry.display_name}.")


def read_file_text(window: "NoteCopyPaster", target: SnipcomEntry | Path | str, action_name: str) -> str | None:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return None

    if entry.backend == "json_command":
        return entry.body
    if entry.is_command:
        assert entry.command_id is not None
        try:
            return window.repository.command_store.get_command(entry.command_id).body
        except KeyError:
            window.refresh_table()
            QMessageBox.warning(window, "Missing command", f"{entry.display_name} no longer exists.")
            return None
    if entry.is_folder:
        QMessageBox.warning(window, action_name, "Folders do not have inline text content.")
        return None

    assert entry.path is not None
    try:
        return window.repository.read_text(entry.path)
    except UnicodeDecodeError:
        QMessageBox.warning(window, action_name, f"{entry.display_name} is not UTF-8 text.")
        return None
    except OSError as exc:
        QMessageBox.critical(window, action_name, str(exc))
        return None


def read_entry_text_quiet(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str | None:
    entry = window.entry_for(target)
    if entry is None:
        return None
    if entry.is_command:
        if entry.command_id is None:
            return entry.body  # json_command: body already on entry
        try:
            return window.repository.command_store.get_command(entry.command_id).body
        except KeyError:
            return None
    if entry.is_folder:
        return None
    assert entry.path is not None
    try:
        return window.repository.read_text(entry.path)
    except (OSError, UnicodeDecodeError):
        return None


def write_entry_text(window: "NoteCopyPaster", target: SnipcomEntry | Path | str, content: str, action_name: str) -> bool:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return False
    try:
        if entry.backend == "json_command":
            window.repository.user_command_store.update(entry.source_ref, body=content)
        elif entry.is_command:
            assert entry.command_id is not None
            window.repository.command_store.update_command(entry.command_id, body=content)
        elif entry.is_folder:
            QMessageBox.warning(window, action_name, "Folders do not support text editing.")
            return False
        else:
            assert entry.path is not None
            window.repository.write_text(entry.path, content)
        return True
    except OSError as exc:
        QMessageBox.critical(window, action_name, str(exc))
        return False


def copy_content(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        return
    content = read_file_text(window, entry, "Copy failed")
    if content is None:
        return

    QApplication.clipboard().setText(content)
    window.record_command_usage(entry, event_kind="copy")
    window.show_status(f"Copied content from {entry.display_name}.")


def paste_clipboard_content(window: "NoteCopyPaster", target: SnipcomEntry | Path | str, position: str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        return
    current_content = read_file_text(window, entry, "Paste failed")
    if current_content is None:
        return

    clipboard_content = QApplication.clipboard().text()
    if position == "top":
        new_content = clipboard_content + current_content
        status_message = f"Prepended clipboard content into {entry.display_name}."
        undo_message = f"Undid prepend into {entry.display_name}."
    elif position == "bottom":
        new_content = current_content + clipboard_content
        status_message = f"Appended clipboard content into {entry.display_name}."
        undo_message = f"Undid append into {entry.display_name}."
    else:
        new_content = clipboard_content
        status_message = f"Replaced the content of {entry.display_name} with clipboard text."
        undo_message = f"Undid replacement of {entry.display_name}."

    if not write_entry_text(window, entry, new_content, "Paste failed"):
        return

    window.push_undo(
        {
            "type": "restore_entry_content",
            "entry_id": entry.entry_id,
            "previous_content": current_content,
            "message": undo_message,
        }
    )
    window.refresh_table()
    window.show_status(status_message)


def prepend_paste(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    paste_clipboard_content(window, target, "top")


def append_paste(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    paste_clipboard_content(window, target, "bottom")


def rewrite_paste(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    paste_clipboard_content(window, target, "replace")


def build_command_text(
    window: "NoteCopyPaster",
    target: SnipcomEntry | Path | str,
    action_name: str,
) -> tuple[str, dict[str, object]] | tuple[None, None]:
    entry = window.entry_for(target)
    if entry is None:
        return None, None
    if entry.is_folder:
        QMessageBox.warning(window, action_name, "Folders cannot be launched or sent as commands.")
        return None, None
    content = read_file_text(window, entry, action_name)
    if content is None:
        return None, None

    command = content.strip()
    if not command:
        window.show_toast(f"{entry.display_name} is empty.")
        return None, None

    launch_options = window.launch_options_for(entry)
    if launch_options["ask_extra_arguments"]:
        extra_arguments, accepted = QInputDialog.getText(
            window,
            "Extra launch arguments",
            "Extra arguments to append for this action:",
        )
        if not accepted:
            return None, None
        extra_arguments = extra_arguments.strip()
        if extra_arguments:
            command = f"{command} {extra_arguments}"

    return command, launch_options
