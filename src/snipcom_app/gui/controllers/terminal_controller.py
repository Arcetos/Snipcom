from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox

from ...integration.linked_terminal import (
    create_linked_terminal_session,
    dispatch_linked_terminal_command,
    launch_linked_terminal_session,
    linked_terminal_root_dir,
    linked_terminal_session_is_active,
    read_linked_terminal_last_cwd,
    read_linked_terminal_last_output,
)
from ...core.safety import evaluate_command_risk
from .terminal_poll_mixin import TerminalPollMixin
from .terminal_ai_mixin import TerminalAIMixin

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class TerminalController(TerminalPollMixin, TerminalAIMixin):
    _SESSION_CACHE_TTL = 0.4  # seconds

    def __init__(self, window: "NoteCopyPaster", *, terminal_suggestion_count: int) -> None:
        self.window = window
        self.terminal_suggestion_count = terminal_suggestion_count
        self._last_synced_ai_signature: tuple[str, tuple[str, ...], str] = ("", (), "")
        self._last_selector_signature: tuple[str, ...] = ()
        self._session_cache: dict | None = None
        self._session_cache_at: float = 0.0

    def _get_current_session(self) -> dict | None:
        now = time.monotonic()
        if self._session_cache is not None and (now - self._session_cache_at) < self._SESSION_CACHE_TTL:
            return self._session_cache
        self._session_cache = self.window.current_linked_terminal_session()
        self._session_cache_at = now
        return self._session_cache

    def invalidate_session_cache(self) -> None:
        self._session_cache = None
        self._session_cache_at = 0.0

    def _debug_enabled(self) -> bool:
        return (
            os.environ.get("SNIPCOM_DEBUG_TERMINAL", "").strip() == "1"
            or os.environ.get("COMMANDSNIP_DEBUG_TERMINAL", "").strip() == "1"
        )

    def _debug_log(self, message: str) -> None:
        if self._debug_enabled():
            print(f"[Snipcom][terminal] {message}", file=sys.stderr, flush=True)

    def dispatch_command_to_linked_terminal(self, session_dir: Path, label: str, command: str) -> tuple[bool, str]:
        window = self.window
        delivery = dispatch_linked_terminal_command(session_dir, command)
        if delivery == "queued" and not linked_terminal_session_is_active(session_dir):
            if not launch_linked_terminal_session(
                window.settings,
                session_dir,
                label,
                chooser=lambda: window.choose_terminal_executable(),
            ):
                return False, "launch_failed"
            return True, "restarted_and_queued"
        return True, delivery

    def refresh_linked_terminal_toolbar(self) -> None:
        window = self.window
        started_at = time.monotonic()
        sessions = window.active_linked_terminal_sessions()
        if not sessions:
            window.current_linked_terminal_dir = None
            self._last_selector_signature = ()
            self._reset_terminal_poll_cache()
            self.clear_terminal_inline_ai_state()
            window.terminal_toolbar_widget.hide()
            if window.pending_append_output is not None:
                window.cancel_append_output_selection()
            return

        session = window.current_linked_terminal_session()
        if session is None:
            return

        selector_signature = tuple(str(linked_session["runtime_dir"]) for linked_session in sessions)
        if selector_signature != self._last_selector_signature:
            selector_menu = QMenu(window.terminal_selector_button)
            for linked_session in sessions:
                label = str(linked_session["label"])
                action = window.configure_menu_action(
                    QAction(label, selector_menu),
                    f"Switch the terminal control bar to {label}.",
                )
                action.triggered.connect(
                    lambda _checked=False, session_dir=Path(linked_session["runtime_dir"]): self.select_linked_terminal(
                        session_dir
                    )
                )
                selector_menu.addAction(action)
            window.terminal_selector_button.setMenu(selector_menu if len(sessions) > 1 else None)
            self._last_selector_signature = selector_signature
        selector_label = str(session["label"]).replace("Linked Terminal ", "Terminal Linked ")
        window.terminal_selector_button.setText(selector_label)
        linkbar_text = window.terminal_command_input.text().strip()
        linkbar_request = window.natural_request_text(linkbar_text)
        typed_terminal_request = ""
        if linkbar_request and window.ai_enabled():
            self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
            if window.terminal_inline_ai_suggestion is not None:
                self.sync_linked_terminal_ai_suggestions(
                    request_text=linkbar_request,
                    suggestions=[window.terminal_inline_ai_suggestion.command],
                )
            else:
                self.sync_linked_terminal_ai_suggestions()
        elif linkbar_text:
            self._render_terminal_inline_ai(None, "")
            self.sync_linked_terminal_ai_suggestions()
        else:
            typed_terminal_request = window.natural_request_text(self.current_linked_terminal_typed_text())
            if typed_terminal_request and window.ai_enabled():
                if (
                    window.terminal_inline_ai_request.casefold() != typed_terminal_request.casefold()
                    or (
                        window.terminal_inline_ai_suggestion is None
                        and not window.terminal_inline_ai_error
                    )
                ):
                    should_generate, message = self.should_auto_generate_ai(typed_terminal_request, is_terminal=True)
                    if should_generate:
                        self._debug_log(f"inline AI generate from terminal request: {typed_terminal_request!r}")
                        window.terminal_inline_ai_busy = True
                        suggestion, error_message = window.ai_controller.generate_inline_ai_suggestion(typed_terminal_request)
                        window.terminal_inline_ai_busy = False
                        self._set_terminal_inline_ai_result(
                            typed_terminal_request,
                            suggestion,
                            error_message,
                            generated_now=True,
                        )
                    else:
                        self._set_terminal_inline_ai_result(
                            typed_terminal_request,
                            None,
                            message or "",
                            generated_now=False,
                        )
                self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
                if window.terminal_inline_ai_suggestion is not None:
                    self.sync_linked_terminal_ai_suggestions(
                        request_text=typed_terminal_request,
                        suggestions=[window.terminal_inline_ai_suggestion.command],
                    )
                else:
                    self.sync_linked_terminal_ai_suggestions()
            elif window.ai_enabled():
                window.terminal_ai_suggestion_label.hide()
                self.refresh_passive_terminal_suggestions()
                if window.terminal_passive_suggestions:
                    window.show_terminal_ai_overlay(
                        window.ai_controller.format_terminal_suggestions_overlay(window.terminal_passive_suggestions)
                    )
                    self.sync_linked_terminal_ai_suggestions(
                        suggestions=window.terminal_passive_suggestions[: self.terminal_suggestion_count]
                    )
                else:
                    window.hide_terminal_ai_overlay()
                    self.sync_linked_terminal_ai_suggestions()
            else:
                window.terminal_ai_suggestion_label.hide()
                window.hide_terminal_ai_overlay()
                self.sync_linked_terminal_ai_suggestions()
        window.terminal_toolbar_widget.show()
        elapsed_ms = (time.monotonic() - started_at) * 1000.0
        if elapsed_ms >= 80.0:
            self._debug_log(
                f"refresh toolbar took {elapsed_ms:.1f}ms "
                f"(linkbar_text={bool(linkbar_text)}, linkbar_request={bool(linkbar_request)}, typed_request={bool(typed_terminal_request)})"
            )

    def select_linked_terminal(self, session_dir: Path) -> None:
        window = self.window
        window.current_linked_terminal_dir = session_dir
        self.invalidate_session_cache()
        self._reset_terminal_poll_cache()
        self.clear_terminal_inline_ai_state()
        self.refresh_linked_terminal_toolbar()

    def selected_linked_terminal_output(self) -> tuple[Path, str, str] | None:
        window = self.window
        session = window.current_linked_terminal_session()
        if session is None:
            QMessageBox.warning(window, "No linked terminal", "There is no active linked terminal.")
            return None

        session_dir = Path(session["runtime_dir"])
        label = str(session["label"])
        try:
            output = read_linked_terminal_last_output(session_dir)
        except FileNotFoundError:
            QMessageBox.warning(window, "No output", f"{label} has not captured any output yet.")
            return None
        except OSError as exc:
            QMessageBox.critical(window, "Read output failed", str(exc))
            return None

        if not output.strip():
            QMessageBox.warning(window, "No output", f"{label} did not produce any captured output yet.")
            return None
        return session_dir, label, output

    def open_linked_terminal(self) -> None:
        window = self.window
        session_info = create_linked_terminal_session(linked_terminal_root_dir())
        runtime_dir = Path(session_info["runtime_dir"])
        label = str(session_info["label"])
        if not launch_linked_terminal_session(
            window.settings,
            runtime_dir,
            label,
            chooser=lambda: window.choose_terminal_executable(),
        ):
            QMessageBox.warning(window, "Open failed", f"Could not open {label}.")
            return
        window.current_linked_terminal_dir = runtime_dir
        self.refresh_linked_terminal_toolbar()
        window.show_feedback(f"Opened {label}.")

    def send_terminal_input_command(self) -> None:
        window = self.window
        session = window.current_linked_terminal_session()
        if session is None:
            QMessageBox.warning(window, "No linked terminal", "Open or link a terminal first.")
            return

        command = window.terminal_command_input.text().strip()
        if not command:
            return
        if self.apply_terminal_inline_ai_suggestion():
            return

        typed_entry = window.ai_controller.command_entry_for_terminal_command(command)
        dangerous_flag = bool(typed_entry.dangerous) if typed_entry is not None else False
        risk = evaluate_command_risk(command, dangerous_flag=dangerous_flag)
        if risk.risky and not window.confirm_risky_command(
            action_label="send",
            entry_label=(typed_entry.display_name if typed_entry is not None else "Typed command"),
            command_text=command,
            reasons=risk.reasons,
        ):
            window.show_status("Canceled typed command send.")
            return

        session_dir = Path(session["runtime_dir"])
        label = str(session["label"])
        if not linked_terminal_session_is_active(session_dir):
            window.current_linked_terminal_dir = None
            self.refresh_linked_terminal_toolbar()
            QMessageBox.warning(window, "Linked terminal closed", f"{label} is no longer open.")
            return
        delivery_ok, delivery = self.dispatch_command_to_linked_terminal(session_dir, label, command)
        if not delivery_ok:
            QMessageBox.warning(
                window,
                "Send failed",
                f"Could not restart {label}. The command was left queued.",
            )
            return
        if delivery == "restarted_and_queued":
            window.show_status(f"Restarted {label} and queued the typed command.")
        elif delivery == "sent":
            window.show_status(f"Sent typed command to {label}.")
        else:
            window.show_status(f"Queued typed command for {label}.")
        if typed_entry is not None:
            window.record_command_usage(
                typed_entry,
                event_kind="terminal-input",
                terminal_label=label,
                track_transition=True,
                context={"runtime_dir": str(session_dir)},
            )
        window.observed_terminal_commands[str(session_dir)] = command
        window.terminal_command_input.clear()
        self.clear_terminal_inline_ai_state()
        window.current_linked_terminal_dir = session_dir
        self.refresh_linked_terminal_toolbar()

    def copy_selected_terminal_output(self) -> None:
        window = self.window
        selected_output = self.selected_linked_terminal_output()
        if selected_output is None:
            return
        _session_dir, label, output = selected_output
        QApplication.clipboard().setText(output)
        window.show_status(f"Copied the last output from {label}.")
        window.show_toast(f"Copied output from {label}.")

    def save_selected_terminal_output_to_new_file(self) -> None:
        window = self.window
        selected_output = self.selected_linked_terminal_output()
        if selected_output is None:
            return
        _session_dir, label, output = selected_output
        default_name = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_name, open_after_create, _initial_content = window.prompt_new_file(default_name)
        if file_name is None:
            return
        path = window.create_file_with_content(file_name, output, open_after_create=open_after_create)
        if path is None:
            return
        window.show_status(f"Saved the last output from {label} into {path.name}.")
        window.show_toast(f"Saved {label} output into {path.name}.")

    def begin_append_selected_terminal_output(self) -> None:
        window = self.window
        selected_output = self.selected_linked_terminal_output()
        if selected_output is None:
            return
        session_dir, label, output = selected_output
        window.pending_append_output = {"session_dir": session_dir, "label": label, "output": output}
        window.search_input.setFocus()
        window.search_input.selectAll()
        window.search_controller.update_search_results()
        window.show_status(
            f"Search for a file to append the output from {label}. Press Tab to move into results."
        )
        window.show_toast(f"Choose a file to append {label} output.")
        window.show_instruction_banner(
            "Type to search the chosen file. Press Tab to move to files, and arrows to navigate."
        )

    def latest_terminal_cwd(self) -> str:
        session = self._get_current_session()
        if session is None:
            return ""
        return read_linked_terminal_last_cwd(Path(session["runtime_dir"]))

    def latest_terminal_input(self) -> str:
        session = self._get_current_session()
        if session is None:
            return ""
        return self._read_cached_last_command(Path(session["runtime_dir"]))

    def latest_terminal_output_quiet(self) -> str:
        session = self._get_current_session()
        if session is None:
            return ""
        return self._read_cached_last_output(Path(session["runtime_dir"]))

    def current_linked_terminal_typed_text(self) -> str:
        session = self._get_current_session()
        if session is None:
            return ""
        return self._read_cached_current_input(Path(session["runtime_dir"]))
