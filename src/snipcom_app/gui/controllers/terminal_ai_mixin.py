from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ...integration.linked_terminal import (
    clear_linked_terminal_ai_suggestions,
    write_linked_terminal_ai_suggestions,
)

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class TerminalAIMixin:
    """Mixin providing AI suggestion generation and management for the linked terminal."""

    window: "NoteCopyPaster"
    terminal_suggestion_count: int
    _last_synced_ai_signature: tuple[str, tuple[str, ...], str]

    # These methods are provided by TerminalPollMixin / TerminalController:
    def _debug_log(self, message: str) -> None:
        raise NotImplementedError

    def current_linked_terminal_typed_text(self) -> str:
        raise NotImplementedError

    def latest_terminal_input(self) -> str:
        raise NotImplementedError

    def latest_terminal_output_quiet(self) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Internal rendering helpers                                           #
    # ------------------------------------------------------------------ #

    def _render_terminal_inline_ai(self, suggestion: object | None, error_message: str) -> None:
        window = self.window
        if suggestion is not None:
            command = str(getattr(suggestion, "command", "") or "").strip()
            if command:
                window.terminal_ai_suggestion_label.setText(f"AI suggestion: {command}")
                window.terminal_ai_suggestion_label.show()
                window.show_terminal_ai_overlay(f"1. {command}")
                return
        if error_message:
            window.terminal_ai_suggestion_label.setText(f"AI suggestion: {error_message}")
            window.terminal_ai_suggestion_label.show()
            window.show_terminal_ai_overlay(error_message)
            return
        window.terminal_ai_suggestion_label.hide()
        window.hide_terminal_ai_overlay()

    def _set_terminal_inline_ai_result(
        self,
        request_text: str,
        suggestion: object | None,
        error_message: str,
        *,
        generated_now: bool,
    ) -> None:
        window = self.window
        window.terminal_inline_ai_request = request_text
        if generated_now:
            window.terminal_inline_ai_last_generated_request = request_text
            window.terminal_inline_ai_last_generated_at = time.monotonic()
        window.terminal_inline_ai_suggestion = suggestion
        window.terminal_inline_ai_error = error_message

    # ------------------------------------------------------------------ #
    # State management                                                     #
    # ------------------------------------------------------------------ #

    def clear_terminal_inline_ai_state(self) -> None:
        window = self.window
        window.terminal_inline_ai_timer.stop()
        window.terminal_inline_ai_request = ""
        window.terminal_inline_ai_suggestion = None
        window.terminal_inline_ai_error = ""
        window.terminal_inline_ai_busy = False
        window.terminal_ai_suggestion_label.hide()
        window.hide_terminal_ai_overlay()
        session = window.current_linked_terminal_session()
        if session is not None:
            try:
                clear_linked_terminal_ai_suggestions(Path(session["runtime_dir"]))
            except OSError:
                pass
        self._last_synced_ai_signature = ("", (), "")

    def sync_linked_terminal_ai_suggestions(
        self, *, request_text: str = "", suggestions: list[str] | None = None
    ) -> None:
        window = self.window
        session = window.current_linked_terminal_session()
        if session is None:
            return
        session_dir = Path(session["runtime_dir"])
        normalized_suggestions = tuple(suggestion.strip() for suggestion in (suggestions or []) if suggestion.strip())
        signature = (str(session_dir), normalized_suggestions, request_text.strip())
        if signature == self._last_synced_ai_signature:
            return
        try:
            if normalized_suggestions:
                write_linked_terminal_ai_suggestions(session_dir, request_text, list(normalized_suggestions))
            else:
                clear_linked_terminal_ai_suggestions(session_dir)
        except OSError:
            return
        self._last_synced_ai_signature = signature

    # ------------------------------------------------------------------ #
    # Generation guard                                                     #
    # ------------------------------------------------------------------ #

    def should_auto_generate_ai(self, request_text: str, *, is_terminal: bool) -> tuple[bool, str]:
        window = self.window
        cleaned = request_text.strip()
        if len(cleaned) < 8:
            return False, "Keep typing for AI suggestion..."
        if is_terminal:
            if window.terminal_inline_ai_busy:
                return False, "AI suggestion is still generating..."
            if (
                window.terminal_inline_ai_last_generated_request.casefold() == cleaned.casefold()
                and (time.monotonic() - window.terminal_inline_ai_last_generated_at) < 6.0
            ):
                return False, ""
        else:
            if window.search_inline_ai_busy:
                return False, "AI suggestion is still generating..."
            if (
                window.search_inline_ai_last_generated_request.casefold() == cleaned.casefold()
                and (time.monotonic() - window.search_inline_ai_last_generated_at) < 6.0
            ):
                return False, ""
        return True, ""

    # ------------------------------------------------------------------ #
    # Inline AI — timer-driven generation                                  #
    # ------------------------------------------------------------------ #

    def refresh_terminal_inline_ai_suggestion(self) -> None:
        window = self.window
        request_text = window.natural_request_text(window.terminal_command_input.text())
        if not request_text or not window.ai_enabled():
            self.clear_terminal_inline_ai_state()
            return
        should_generate, message = self.should_auto_generate_ai(request_text, is_terminal=True)
        if not should_generate:
            if message:
                self._set_terminal_inline_ai_result(
                    request_text,
                    window.terminal_inline_ai_suggestion,
                    message,
                    generated_now=False,
                )
                self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
            return
        self._debug_log(f"inline AI generate from linkbar request: {request_text!r}")
        window.terminal_inline_ai_busy = True
        started_at = time.monotonic()
        suggestion, error_message = window.ai_controller.generate_inline_ai_suggestion(request_text)
        window.terminal_inline_ai_busy = False
        self._debug_log(f"inline AI result in {(time.monotonic() - started_at) * 1000.0:.1f}ms")
        self._set_terminal_inline_ai_result(request_text, suggestion, error_message, generated_now=True)
        self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)

    def handle_terminal_input_text_changed(self, text: str) -> None:
        window = self.window
        request_text = window.natural_request_text(text)
        if not request_text:
            self.clear_terminal_inline_ai_state()
            if not text.strip():
                self.refresh_linked_terminal_toolbar()
            return
        if not window.ai_enabled():
            window.terminal_inline_ai_timer.stop()
            self._set_terminal_inline_ai_result(
                request_text,
                None,
                "AI is disabled. Enable it in Settings > Options > AI.",
                generated_now=False,
            )
            self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
            return
        should_generate, message = self.should_auto_generate_ai(request_text, is_terminal=True)
        self._set_terminal_inline_ai_result(
            request_text,
            None,
            message or "Generating AI suggestion...",
            generated_now=False,
        )
        self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
        if should_generate:
            window.terminal_inline_ai_timer.start(500)
        else:
            window.terminal_inline_ai_timer.stop()

    def refresh_linked_terminal_toolbar(self) -> None:
        raise NotImplementedError  # provided by TerminalController

    # ------------------------------------------------------------------ #
    # Apply suggestion                                                     #
    # ------------------------------------------------------------------ #

    def apply_terminal_inline_ai_suggestion_index(self, index: int) -> bool:
        window = self.window
        if index != 0 or window.terminal_inline_ai_suggestion is None:
            return False
        window.terminal_command_input.setText(window.terminal_inline_ai_suggestion.command)
        window.terminal_command_input.setFocus()
        window.terminal_command_input.selectAll()
        return True

    def apply_terminal_suggestion_index(self, index: int) -> bool:
        window = self.window
        if window.natural_request_text(window.terminal_command_input.text()):
            return self.apply_terminal_inline_ai_suggestion_index(index)
        if index < 0 or index >= len(window.terminal_passive_suggestions):
            return False
        window.terminal_command_input.setText(window.terminal_passive_suggestions[index])
        window.terminal_command_input.setFocus()
        window.terminal_command_input.selectAll()
        return True

    def apply_terminal_inline_ai_suggestion(self) -> bool:
        window = self.window
        request_text = window.natural_request_text(window.terminal_command_input.text())
        if not request_text:
            return False
        if not window.ai_enabled():
            self._set_terminal_inline_ai_result(
                request_text,
                None,
                "AI is disabled. Enable it in Settings > Options > AI.",
                generated_now=False,
            )
            self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
            window.show_status(window.terminal_inline_ai_error)
            return True
        if not window.ai_controller.inline_suggestion_matches_request(
            window.terminal_inline_ai_suggestion,
            request_text=request_text,
            cached_request=window.terminal_inline_ai_request,
        ):
            suggestion, error_message = window.ai_controller.generate_inline_ai_suggestion(request_text)
            self._set_terminal_inline_ai_result(request_text, suggestion, error_message, generated_now=False)
            self._render_terminal_inline_ai(window.terminal_inline_ai_suggestion, window.terminal_inline_ai_error)
        if window.terminal_inline_ai_suggestion is None:
            if window.terminal_inline_ai_error:
                window.show_status(window.terminal_inline_ai_error)
            return True
        return self.apply_terminal_inline_ai_suggestion_index(0)

    # ------------------------------------------------------------------ #
    # Passive suggestions                                                  #
    # ------------------------------------------------------------------ #

    def refresh_passive_terminal_suggestions(self) -> None:
        window = self.window
        if not window.ai_enabled():
            window.terminal_passive_suggestions = []
            return
        if window.natural_request_text(window.terminal_command_input.text()):
            return
        typed_text = self.current_linked_terminal_typed_text().strip()
        if window.natural_request_text(typed_text):
            return
        latest_input = self.latest_terminal_input().strip()
        latest_output = self.latest_terminal_output_quiet().strip()
        signature = (latest_input, latest_output, typed_text)
        if latest_input:
            self.observe_direct_terminal_command(latest_input)
        if signature == window.terminal_passive_signature and window.terminal_passive_suggestions:
            return
        window.terminal_passive_signature = signature
        window.terminal_passive_suggestions = window.ai_controller.passive_terminal_suggestions(typed_prefix=typed_text)

    def observe_direct_terminal_command(self, command: str) -> None:
        window = self.window
        session = window.current_linked_terminal_session()
        if session is None:
            return
        session_dir = Path(session["runtime_dir"])
        runtime_key = str(session_dir)
        cleaned_command = command.strip()
        if not cleaned_command:
            return
        if window.observed_terminal_commands.get(runtime_key, "") == cleaned_command:
            return
        window.observed_terminal_commands[runtime_key] = cleaned_command
        entry = window.ai_controller.command_entry_for_terminal_command(cleaned_command)
        if entry is None:
            return
        window.record_command_usage(
            entry,
            event_kind="terminal-input",
            terminal_label=str(session["label"]),
            track_transition=True,
            context={"runtime_dir": runtime_key, "observed": True},
        )
