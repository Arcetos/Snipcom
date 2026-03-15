from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ...integration.linked_terminal import (
    linked_terminal_last_command_path,
    read_linked_terminal_current_input,
    read_linked_terminal_last_output,
)

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class TerminalPollMixin:
    """Mixin providing debounced filesystem reads for linked-terminal session state."""

    window: "NoteCopyPaster"

    def _debug_log(self, message: str) -> None:
        raise NotImplementedError  # provided by TerminalController

    def _reset_terminal_poll_cache(self) -> None:
        window = self.window
        window._terminal_last_command_cache = {"session": "", "value": "", "checked_at": 0.0}
        window._terminal_current_input_cache = {"session": "", "value": "", "checked_at": 0.0}
        window._terminal_last_output_cache = {
            "session": "",
            "value": "",
            "checked_at": 0.0,
            "command": "",
        }

    def _read_cached_last_command(self, session_dir: Path) -> str:
        window = self.window
        cache = getattr(window, "_terminal_last_command_cache", None)
        if not isinstance(cache, dict):
            self._reset_terminal_poll_cache()
            cache = window._terminal_last_command_cache
        session_key = str(session_dir)
        now = time.monotonic()
        if cache.get("session") == session_key and (now - float(cache.get("checked_at", 0.0) or 0.0)) < 0.8:
            return str(cache.get("value", "") or "")
        try:
            started_at = time.monotonic()
            value = linked_terminal_last_command_path(session_dir).read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        else:
            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            if elapsed_ms >= 20.0:
                self._debug_log(f"read last command took {elapsed_ms:.1f}ms")
        cache.update({"session": session_key, "value": value, "checked_at": now})
        return value

    def _read_cached_current_input(self, session_dir: Path) -> str:
        window = self.window
        cache = getattr(window, "_terminal_current_input_cache", None)
        if not isinstance(cache, dict):
            self._reset_terminal_poll_cache()
            cache = window._terminal_current_input_cache
        session_key = str(session_dir)
        now = time.monotonic()
        if cache.get("session") == session_key and (now - float(cache.get("checked_at", 0.0) or 0.0)) < 0.8:
            return str(cache.get("value", "") or "")
        try:
            started_at = time.monotonic()
            value = read_linked_terminal_current_input(session_dir).strip()
        except OSError:
            value = ""
        else:
            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            if elapsed_ms >= 20.0:
                self._debug_log(f"read current input took {elapsed_ms:.1f}ms")
        cache.update({"session": session_key, "value": value, "checked_at": now})
        return value

    def _read_cached_last_output(self, session_dir: Path) -> str:
        window = self.window
        cache = getattr(window, "_terminal_last_output_cache", None)
        if not isinstance(cache, dict):
            self._reset_terminal_poll_cache()
            cache = window._terminal_last_output_cache
        session_key = str(session_dir)
        current_command = self._read_cached_last_command(session_dir)
        now = time.monotonic()
        if (
            cache.get("session") == session_key
            and cache.get("command") == current_command
            and (now - float(cache.get("checked_at", 0.0) or 0.0)) < 3.0
        ):
            return str(cache.get("value", "") or "")
        try:
            started_at = time.monotonic()
            value = read_linked_terminal_last_output(session_dir).strip()
        except OSError:
            value = ""
        else:
            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            if elapsed_ms >= 20.0:
                self._debug_log(f"read last output took {elapsed_ms:.1f}ms")
        cache.update(
            {
                "session": session_key,
                "value": value,
                "checked_at": now,
                "command": current_command,
            }
        )
        return value
