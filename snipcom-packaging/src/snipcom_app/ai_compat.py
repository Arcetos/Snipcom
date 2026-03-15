"""Deprecated AI compatibility helpers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout

from .ai import AIProviderError, generate_ollama_command

if TYPE_CHECKING:
    from .ai_controller import AiController


def open_deprecated_ai_suggestion_dialog(controller: "AiController") -> None:
    window = controller.window
    if not window.ai_enabled():
        QMessageBox.information(window, "AI disabled", "Enable local AI first in Settings > Options > AI.")
        return
    connection_ok, connection_message = controller.check_ai_connection()
    if not connection_ok:
        QMessageBox.warning(window, "AI unavailable", connection_message)
        return
    if window.current_linked_terminal_session() is None:
        QMessageBox.warning(window, "No linked terminal", "Open a linked terminal first to generate the next likely command.")
        return

    dialog = QDialog(window)
    dialog.setWindowTitle("AI Suggest Command")
    dialog.resize(620, 420)
    layout = QVBoxLayout(dialog)

    request_label = QLabel("Optional request")
    request_input = QPlainTextEdit()
    request_input.setPlaceholderText("Describe what you want next, or leave this blank to use the terminal context only...")
    request_input.setFixedHeight(96)

    output_label = QLabel("Generated command")
    output_output = QPlainTextEdit()
    output_output.setReadOnly(True)

    status_label = QLabel(connection_message)
    status_label.setWordWrap(True)

    button_row = QHBoxLayout()
    generate_button = QPushButton("Generate")
    regenerate_button = QPushButton("Regenerate")
    copy_button = QPushButton("Copy")
    send_button = QPushButton("Send to Linked Terminal")
    add_button = QPushButton("Add as Family")
    close_button = QPushButton("Cancel")
    button_row.addWidget(generate_button)
    button_row.addWidget(regenerate_button)
    button_row.addWidget(copy_button)
    button_row.addWidget(send_button)
    button_row.addWidget(add_button)
    button_row.addStretch(1)
    button_row.addWidget(close_button)

    layout.addWidget(request_label)
    layout.addWidget(request_input)
    layout.addWidget(output_label)
    layout.addWidget(output_output, 1)
    layout.addWidget(status_label)
    layout.addLayout(button_row)

    current_suggestion: dict[str, object | None] = {"result": None}

    def run_generation() -> None:
        user_request = request_input.toPlainText().strip()
        if user_request:
            window.search_controller.remember_search_query(user_request)
        context = controller.build_ai_suggestion_context(user_request)
        if not any(
            (
                context.user_request.strip(),
                context.last_terminal_input.strip(),
                context.last_terminal_output.strip(),
                any(query.strip() for query in context.recent_searches),
                any(command.strip() for command in context.related_commands),
            )
        ):
            QMessageBox.warning(window, "Not enough context", "Provide a short request or use a linked terminal with recent activity first.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            suggestion = generate_ollama_command(
                window.ai_endpoint(),
                window.ai_model(),
                context,
                timeout=window.ai_timeout_seconds(),
            )
        except AIProviderError as exc:
            current_suggestion["result"] = None
            output_output.clear()
            status_label.setText(str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        current_suggestion["result"] = suggestion
        output_output.setPlainText(suggestion.command)
        status_message = f"Generated with {suggestion.model}."
        if suggestion.confidence_low:
            status_message += " Output was normalized from a longer response."
        status_label.setText(status_message)

    def copy_generated() -> None:
        suggestion = current_suggestion["result"]
        if suggestion is None:
            return
        QApplication.clipboard().setText(suggestion.command)
        window.show_status("Copied AI-generated command.")
        window.show_toast("Copied AI-generated command.")

    def send_generated() -> None:
        suggestion = current_suggestion["result"]
        if suggestion is None:
            return
        session = window.current_linked_terminal_session()
        if session is None:
            QMessageBox.warning(window, "No linked terminal", "Open or select a linked terminal first.")
            return
        session_dir = Path(session["runtime_dir"])
        label = str(session["label"])
        delivery_ok, delivery = window.terminal_controller.dispatch_command_to_linked_terminal(
            session_dir,
            label,
            suggestion.command,
        )
        window.observed_terminal_commands[str(session_dir)] = suggestion.command
        if not delivery_ok:
            QMessageBox.warning(window, "Send failed", f"Could not start {label}. The command was left queued.")
            return
        window.current_linked_terminal_dir = session_dir
        window.terminal_controller.refresh_linked_terminal_toolbar()
        if delivery == "restarted_and_queued":
            window.show_status(f"Started {label} and queued AI-generated command.")
            window.show_toast(f"Queued AI-generated command for {label}.")
        elif delivery == "queued":
            window.show_status(f"Queued AI-generated command for {label}.")
            window.show_toast(f"Queued AI-generated command for {label}.")
        else:
            window.show_status(f"Sent AI-generated command to {label}.")
            window.show_toast(f"Sent AI-generated command to {label}.")

    def add_generated() -> None:
        suggestion = current_suggestion["result"]
        if suggestion is None:
            return
        controller.add_ai_generated_command_to_workflow(suggestion)

    generate_button.clicked.connect(run_generation)
    regenerate_button.clicked.connect(run_generation)
    copy_button.clicked.connect(copy_generated)
    send_button.clicked.connect(send_generated)
    add_button.clicked.connect(add_generated)
    close_button.clicked.connect(dialog.reject)

    dialog.exec()
