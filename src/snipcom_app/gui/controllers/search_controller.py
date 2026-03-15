from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem, QMenu

from ...core.helpers import search_snippet

if TYPE_CHECKING:
    from ...core.repository import SnipcomEntry
    from ..main_window import NoteCopyPaster


class SearchController:
    def __init__(self, window: "NoteCopyPaster") -> None:
        self.window = window

    def update_search_results(self) -> None:
        window = self.window
        query = window.search_input.text().strip()
        window.title_results.clear()
        window.content_results.clear()
        window.command_results.clear()
        window.command_results_secondary.clear()

        if not query:
            window.search_inline_ai_request = ""
            window.search_inline_ai_suggestion = None
            window.search_inline_ai_error = ""
            window.title_group.setTitle("Found in title (0)")
            window.content_group.setTitle("Found inside content (0)")
            window.command_group.setTitle("Suggested commands (0)")
            window.search_results_widget.setVisible(False)
            return

        natural_request = window.natural_request_text(query)
        if natural_request and window.ai_enabled():
            if window.search_inline_ai_request.casefold() != natural_request.casefold():
                window.search_inline_ai_error = "Generating AI suggestion..."
            if (
                window.search_inline_ai_suggestion is not None
                and window.search_inline_ai_request.casefold() == natural_request.casefold()
            ):
                item = QListWidgetItem(window.search_inline_ai_suggestion.command)
                item.setData(Qt.ItemDataRole.UserRole, "__ai_inline__")
                window.command_results.addItem(item)
            elif window.search_inline_ai_error:
                item = QListWidgetItem(window.search_inline_ai_error)
                item.setData(Qt.ItemDataRole.UserRole, "__ai_inline_pending__")
                item.setForeground(QColor(196, 203, 214))
                window.command_results.addItem(item)
            window.title_group.setTitle("Found in title (0)")
            window.content_group.setTitle("Found inside content (0)")
            window.command_group.setTitle(
                "Suggested commands (1)" if window.command_results.count() else "Suggested commands (0)"
            )
            window.search_results_widget.setVisible(True)
            return

        title_matches: list[SnipcomEntry] = []
        content_matches: list[tuple[SnipcomEntry, str]] = []
        command_matches: list[tuple[int, SnipcomEntry]] = []
        query_casefold = query.casefold()
        entries = window.active_entries()
        if window.pending_append_output is not None:
            entries = [entry for entry in entries if entry.is_file]

        for entry in entries:
            if query_casefold in entry.display_name.casefold():
                title_matches.append(entry)
                continue

            if entry.is_command:
                content = entry.body
            else:
                content = window.read_entry_text_quiet(entry)
                if content is None:
                    continue

            if query_casefold in content.casefold():
                content_matches.append((entry, search_snippet(content, query)))

        if window.pending_append_output is None:
            command_entries = window.repository.catalog_entries(include_active_commands=True)
            usage_counts = window.repository.command_store.usage_counts()
            terminal_label = window.selected_linked_terminal_label()
            terminal_runtime = str(window.current_linked_terminal_dir or "")
            current_terminal_command_id = (
                window.repository.command_store.latest_terminal_command_id(
                    terminal_label, terminal_runtime=terminal_runtime
                )
                if terminal_label or terminal_runtime
                else None
            )
            transition_weights = (
                window.repository.command_store.transition_weights(
                    current_terminal_command_id, terminal_label=terminal_label
                )
                if current_terminal_command_id is not None
                else {}
            )
            seen_entry_ids: set[str] = set()
            for entry in command_entries:
                if entry.entry_id in seen_entry_ids:
                    continue
                seen_entry_ids.add(entry.entry_id)
                haystacks = [
                    entry.display_name.casefold(),
                    entry.tag_text.casefold(),
                    entry.family_key.casefold(),
                    entry.source_kind.casefold(),
                ]
                content = entry.body
                if content:
                    haystacks.append(content.casefold())
                if not any(query_casefold in haystack for haystack in haystacks):
                    continue
                score = self.command_search_score(
                    entry,
                    query_casefold,
                    content or "",
                    usage_count=usage_counts.get(entry.command_id or -1, 0),
                    transition_weight=transition_weights.get(entry.command_id or -1, 0),
                )
                command_matches.append((score, entry))

        for entry in sorted(title_matches, key=lambda item: item.display_name.casefold()):
            item = QListWidgetItem(self.search_display_text(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            if entry.dangerous:
                item.setForeground(QColor(255, 188, 104))
            window.title_results.addItem(item)

        for entry, snippet in sorted(content_matches, key=lambda item: item[0].display_name.casefold()):
            item = QListWidgetItem(f"{self.search_display_text(entry)} | {snippet}")
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            if entry.dangerous:
                item.setForeground(QColor(255, 188, 104))
            window.content_results.addItem(item)

        visible_command_matches = sorted(
            command_matches,
            key=lambda item: (-item[0], item[1].display_name.casefold(), item[1].entry_id),
        )[:26]
        for _score, entry in visible_command_matches:
            item = QListWidgetItem(self.command_search_display_text(entry))
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            if entry.dangerous:
                item.setForeground(QColor(255, 188, 104))
            window.command_results.addItem(item)

        window.title_group.setTitle(f"Found in title ({len(title_matches)})")
        window.content_group.setTitle(f"Found inside content ({len(content_matches)})")
        window.command_group.setTitle(f"Suggested commands ({len(command_matches)})")
        window.search_results_widget.setVisible(True)

    def command_search_score(
        self,
        entry: "SnipcomEntry",
        query_casefold: str,
        content: str,
        *,
        usage_count: int = 0,
        transition_weight: int = 0,
    ) -> int:
        window = self.window
        score = 0
        title = entry.display_name.casefold()
        tags = entry.tag_text.casefold()
        family = entry.family_key.casefold()
        if title == query_casefold:
            score += 120
        elif title.startswith(query_casefold):
            score += 90
        elif query_casefold in title:
            score += 70
        if query_casefold in tags:
            score += 35
        if query_casefold in family:
            score += 30
        if query_casefold in content.casefold():
            score += 20
        score += min(usage_count, 20) * 3
        score += min(transition_weight, 12) * 8
        if window.filter_controller.is_pinned_family(entry.family_key):
            score += 40
        if window.selected_family_filter and entry.family_key == window.selected_family_filter:
            score += 50
        if not entry.catalog_only:
            score += 25
        return score

    def command_search_display_text(self, entry: "SnipcomEntry") -> str:
        description = self.window.description_for(entry)
        if description:
            return f"{entry.display_name} . {description}"
        return entry.display_name

    def search_display_text(self, target: "SnipcomEntry | Path | str") -> str:
        window = self.window
        entry = window.entry_for(target)
        if entry is None:
            return "Missing entry"
        description = window.description_for(entry)
        display_name = entry.display_name if not description else f"{entry.display_name} . {description}"
        tag = window.tag_for(entry)
        if tag:
            return f"{display_name} [{tag}]"
        return display_name

    def remember_search_query(self, query: str) -> None:
        window = self.window
        cleaned_query = query.strip()
        if not cleaned_query:
            return
        updated = [cleaned_query]
        updated.extend(
            existing
            for existing in window.recent_search_queries
            if existing.casefold() != cleaned_query.casefold()
        )
        window.recent_search_queries = updated[:2]
        window.settings["recent_search_queries"] = list(window.recent_search_queries)
        window.save_settings()

    def _set_search_inline_ai_result(
        self,
        request_text: str,
        suggestion: object | None,
        error_message: str,
        *,
        generated_now: bool,
    ) -> None:
        window = self.window
        window.search_inline_ai_request = request_text
        if generated_now:
            window.search_inline_ai_last_generated_request = request_text
            window.search_inline_ai_last_generated_at = time.monotonic()
        window.search_inline_ai_suggestion = suggestion
        window.search_inline_ai_error = error_message

    def handle_search_input_text_changed(self, text: str) -> None:
        window = self.window
        request_text = window.natural_request_text(text)
        if not request_text:
            window.clear_search_inline_ai_state()
            return
        if not window.ai_enabled():
            window.search_inline_ai_timer.stop()
            self._set_search_inline_ai_result(
                request_text,
                None,
                "AI is disabled. Enable it in Settings > Options > AI.",
                generated_now=False,
            )
            self.update_search_results()
            return
        should_generate, message = window.terminal_controller.should_auto_generate_ai(request_text, is_terminal=False)
        self._set_search_inline_ai_result(
            request_text,
            None,
            message or "Generating AI suggestion...",
            generated_now=False,
        )
        if should_generate:
            window.search_inline_ai_timer.start(500)
        else:
            window.search_inline_ai_timer.stop()
            self.update_search_results()

    def refresh_search_inline_ai_suggestion(self) -> None:
        window = self.window
        request_text = window.natural_request_text(window.search_input.text())
        if not request_text or not window.ai_enabled():
            window.search_inline_ai_request = ""
            window.search_inline_ai_suggestion = None
            window.search_inline_ai_error = ""
            self.update_search_results()
            return
        should_generate, message = window.terminal_controller.should_auto_generate_ai(request_text, is_terminal=False)
        if not should_generate:
            if message:
                window.search_inline_ai_error = message
            self.update_search_results()
            return
        window.search_inline_ai_busy = True
        suggestion, error_message = window.ai_controller.generate_inline_ai_suggestion(
            request_text, include_terminal_context=False
        )
        window.search_inline_ai_busy = False
        self._set_search_inline_ai_result(request_text, suggestion, error_message, generated_now=True)
        self.update_search_results()

    def apply_search_inline_ai_suggestion(self) -> bool:
        window = self.window
        request_text = window.natural_request_text(window.search_input.text())
        if not request_text:
            return False
        if not window.ai_enabled():
            window.search_inline_ai_error = "AI is disabled. Enable it in Settings > Options > AI."
            self.update_search_results()
            window.show_status(window.search_inline_ai_error)
            return True
        if not window.ai_controller.inline_suggestion_matches_request(
            window.search_inline_ai_suggestion,
            request_text=request_text,
            cached_request=window.search_inline_ai_request,
        ):
            suggestion, error_message = window.ai_controller.generate_inline_ai_suggestion(
                request_text, include_terminal_context=False
            )
            self._set_search_inline_ai_result(request_text, suggestion, error_message, generated_now=False)
            self.update_search_results()
        if window.search_inline_ai_suggestion is None:
            if window.search_inline_ai_error:
                window.show_status(window.search_inline_ai_error)
            return True
        window.search_input.setText(window.search_inline_ai_suggestion.command)
        window.search_input.setFocus()
        window.search_input.selectAll()
        window.search_inline_ai_suggestion = None
        window.search_inline_ai_error = ""
        window.search_inline_ai_request = ""
        return True

    def focus_search_result(self, item: QListWidgetItem) -> None:
        window = self.window
        entry_id = str(item.data(Qt.ItemDataRole.UserRole))
        if entry_id == "__ai_inline__":
            self.apply_search_inline_ai_suggestion()
            return
        if entry_id == "__ai_inline_pending__":
            return
        self.remember_search_query(window.search_input.text())
        entry = window.entry_for(entry_id)
        if entry is None:
            return
        if window.pending_append_output is not None:
            window.append_output_to_file(entry)
            return
        window.view_controller.focus_file(entry)

    def open_search_result(self, item: QListWidgetItem) -> None:
        window = self.window
        entry_id = str(item.data(Qt.ItemDataRole.UserRole))
        if entry_id == "__ai_inline__":
            self.apply_search_inline_ai_suggestion()
            return
        if entry_id == "__ai_inline_pending__":
            return
        self.remember_search_query(window.search_input.text())
        entry = window.entry_for(entry_id)
        if entry is None:
            return
        if window.pending_append_output is not None:
            window.append_output_to_file(entry)
            return
        window.view_controller.focus_file(entry)
        window.open_file(entry)

    def clear_quick_search_sequence_state(self) -> None:
        window = self.window
        window.quick_search_sequence_timer.stop()
        window.quick_search_sequence_buffer.clear()
        window.quick_search_pending_action = None

    def quick_search_bindings_for(self, action: str) -> list[list[str]]:
        window = self.window
        bindings = window.quick_search_bindings.get(action, window.quick_search_binding_defaults[action])
        sequences: list[list[str]] = []
        for binding in bindings:
            sequence_text = str(binding).strip()
            if not sequence_text:
                continue
            parts = [part.strip() for part in sequence_text.split(",") if part.strip()]
            if parts:
                sequences.append(parts)
        return sequences

    def quick_search_event_token(self, event) -> str:
        token = QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText).strip()
        if token in {"", "Meta", "Ctrl", "Alt", "Shift"}:
            return ""
        return token

    def quick_search_focus_first_results(self) -> bool:
        window = self.window
        self.remember_search_query(window.search_input.text())
        for widget in (window.command_results, window.title_results, window.content_results):
            if widget.count() > 0:
                widget.setCurrentRow(max(0, widget.currentRow()))
                if widget.currentRow() < 0:
                    widget.setCurrentRow(0)
                widget.setFocus()
                return True
        return False

    def cycle_search_results_focus(self, current: object | None, *, reverse: bool = False) -> bool:
        window = self.window
        widgets = [
            widget
            for widget in (window.command_results, window.title_results, window.content_results)
            if widget.count() > 0
        ]
        if not widgets:
            return False
        if current not in widgets:
            target = widgets[-1] if reverse else widgets[0]
            target.setCurrentRow(max(0, target.currentRow()))
            if target.currentRow() < 0:
                target.setCurrentRow(0)
            target.setFocus()
            return True
        index = widgets.index(current)
        next_index = (index - 1) % len(widgets) if reverse else (index + 1) % len(widgets)
        target = widgets[next_index]
        target.setCurrentRow(max(0, target.currentRow()))
        if target.currentRow() < 0:
            target.setCurrentRow(0)
        target.setFocus()
        return True

    def move_search_selection(self, widget: QListWidget, offset: int) -> bool:
        if widget.count() <= 0:
            return False
        current_row = widget.currentRow()
        if current_row < 0:
            current_row = 0
        widget.setCurrentRow(max(0, min(widget.count() - 1, current_row + offset)))
        widget.setFocus()
        return True

    def show_search_result_context_menu(self, widget: QListWidget, pos=None) -> None:
        """Show action menu for the current search result item (right-click or Enter key)."""
        window = self.window
        item = widget.currentItem()
        if item is None:
            return
        entry_id = str(item.data(Qt.ItemDataRole.UserRole))
        if entry_id in ("__ai_inline__", "__ai_inline_pending__"):
            return
        entry = window.entry_for(entry_id)
        if entry is None:
            return

        menu = QMenu(widget)
        open_action = menu.addAction("Open")
        launch_action = send_action = copy_action = add_to_workflow_action = None

        if entry.is_command:
            launch_action = menu.addAction("Launch in linked terminal")
            send_action = menu.addAction("Send to linked terminal")
            copy_action = menu.addAction("Copy content")
            if entry.catalog_only:
                menu.addSeparator()
                add_to_workflow_action = menu.addAction("Add to workflow")

        if pos is None:
            rect = widget.visualItemRect(item)
            global_pos = widget.mapToGlobal(rect.bottomLeft())
        else:
            global_pos = widget.mapToGlobal(pos)

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is open_action:
            self.remember_search_query(window.search_input.text())
            window.view_controller.focus_file(entry)
            window.open_file(entry)
        elif launch_action and chosen is launch_action:
            window.launch_file_content(entry)
        elif send_action and chosen is send_action:
            window.send_file_content(entry)
        elif copy_action and chosen is copy_action:
            window.copy_content(entry)
        elif add_to_workflow_action and chosen is add_to_workflow_action:
            window.add_command_to_workflow(entry)

    def execute_quick_search_action(self, action: str, source: object) -> bool:
        window = self.window
        if action == "focus_results":
            return self.quick_search_focus_first_results()
        if not isinstance(source, QListWidget):
            return False
        if action == "navigate_up":
            return self.move_search_selection(source, -1)
        if action == "navigate_down":
            return self.move_search_selection(source, 1)
        if action == "navigate_left":
            return self.move_search_selection(source, -1)
        if action == "navigate_right":
            return self.move_search_selection(source, 1)

        current_item = source.currentItem()
        if current_item is None:
            return False
        entry = window.entry_for(str(current_item.data(Qt.ItemDataRole.UserRole)))
        if entry is None or not entry.is_command:
            return False
        if action == "send_command":
            window.send_file_content(entry)
            return True
        if action == "add_to_workspace":
            return window.add_command_to_workflow(entry)
        if action == "launch_command":
            window.launch_file_content(entry)
            return True
        if action == "copy_command":
            window.copy_content(entry)
            return True
        return False

    def finish_pending_quick_search_action(self) -> None:
        action = self.window.quick_search_pending_action
        source = QApplication.focusWidget()
        self.clear_quick_search_sequence_state()
        if action is None or source is None:
            return
        self.execute_quick_search_action(action, source)

    def handle_quick_search_keypress(self, source: object, event, *, allowed_actions: set[str] | None = None) -> bool:
        window = self.window
        token = self.quick_search_event_token(event)
        if not token:
            return False

        candidate_buffer = [*window.quick_search_sequence_buffer, token]
        exact_matches: list[str] = []
        prefix_matches: list[str] = []
        actions_to_check = allowed_actions or set(window.quick_search_binding_defaults)
        for action in actions_to_check:
            for sequence in self.quick_search_bindings_for(action):
                if len(candidate_buffer) > len(sequence):
                    continue
                if candidate_buffer == sequence[: len(candidate_buffer)]:
                    if len(candidate_buffer) == len(sequence):
                        exact_matches.append(action)
                    else:
                        prefix_matches.append(action)

        if not exact_matches and not prefix_matches and window.quick_search_pending_action is not None:
            pending_action = window.quick_search_pending_action
            self.clear_quick_search_sequence_state()
            if self.execute_quick_search_action(pending_action, source):
                return True
            candidate_buffer = [token]
            exact_matches = []
            prefix_matches = []
            for action in actions_to_check:
                for sequence in self.quick_search_bindings_for(action):
                    if len(candidate_buffer) > len(sequence):
                        continue
                    if candidate_buffer == sequence[: len(candidate_buffer)]:
                        if len(candidate_buffer) == len(sequence):
                            exact_matches.append(action)
                        else:
                            prefix_matches.append(action)

        if exact_matches and prefix_matches:
            window.quick_search_sequence_buffer = candidate_buffer
            window.quick_search_pending_action = exact_matches[0]
            window.quick_search_sequence_timer.start(450)
            return True
        if prefix_matches:
            window.quick_search_sequence_buffer = candidate_buffer
            window.quick_search_pending_action = None
            window.quick_search_sequence_timer.start(900)
            return True
        if exact_matches:
            self.clear_quick_search_sequence_state()
            return self.execute_quick_search_action(exact_matches[0], source)

        self.clear_quick_search_sequence_state()
        return False
