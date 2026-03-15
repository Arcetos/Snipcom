from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QPushButton, QToolButton, QWidget

from ..integration.linked_terminal import close_all_linked_terminal_sessions, linked_terminal_root_dir
from ..core.repository import SnipcomEntry

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowInteractionMixin:
    def eventFilter(self: "NoteCopyPaster", source: object, event: object) -> bool:
        table_widget = getattr(self, "table", None)
        instruction_banner = getattr(self, "instruction_banner", None)
        title_results = getattr(self, "title_results", None)
        content_results = getattr(self, "content_results", None)
        command_results = getattr(self, "command_results", None)
        search_lists = {widget for widget in (title_results, content_results, command_results) if widget is not None}
        if instruction_banner is not None and instruction_banner.isVisible() and event.type() in {
            QEvent.Type.KeyPress,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.Wheel,
        }:
            self.presentation_controller.hide_instruction_banner()
        terminal_ai_overlay = getattr(self, "terminal_ai_overlay", None)
        if terminal_ai_overlay is not None and terminal_ai_overlay.isVisible() and event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.Wheel,
        }:
            self.presentation_controller.hide_terminal_ai_overlay()

        if self.pending_append_output is not None and event.type() == QEvent.Type.KeyPress:
            if source is self.search_input:
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.natural_request_text(self.search_input.text()):
                    if self.search_controller.apply_search_inline_ai_suggestion():
                        return True
                if self.search_controller.handle_quick_search_keypress(source, event, allowed_actions={"focus_results"}):
                    return True
                if event.key() == Qt.Key.Key_Tab:
                    if self.search_controller.cycle_search_results_focus(None, reverse=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                        return True
                if event.key() == Qt.Key.Key_Escape:
                    self.cancel_append_output_selection()
                    self.show_status("Canceled append-output selection.")
                    return True
            elif source in search_lists:
                if event.key() == Qt.Key.Key_Tab:
                    if self.search_controller.cycle_search_results_focus(source, reverse=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                        return True
                if self.search_controller.handle_quick_search_keypress(source, event):
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self.cancel_append_output_selection()
                    self.search_input.setFocus()
                    self.show_status("Canceled append-output selection.")
                    return True

        if self.pending_append_output is None and event.type() == QEvent.Type.KeyPress:
            if source is self.terminal_command_input:
                if event.key() in {Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3} and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                    if self.terminal_controller.apply_terminal_suggestion_index(int(event.key()) - int(Qt.Key.Key_1)):
                        return True
                if event.key() == Qt.Key.Key_Escape and self.terminal_ai_overlay.isVisible():
                    self.presentation_controller.hide_terminal_ai_overlay()
                    return True
            if source is self.search_input:
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.natural_request_text(self.search_input.text()):
                    if self.search_controller.apply_search_inline_ai_suggestion():
                        return True
                if self.search_controller.handle_quick_search_keypress(source, event, allowed_actions={"focus_results"}):
                    return True
                if event.key() == Qt.Key.Key_Tab:
                    if self.search_controller.cycle_search_results_focus(None, reverse=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                        return True
            elif source in search_lists:
                if event.key() == Qt.Key.Key_Tab:
                    if self.search_controller.cycle_search_results_focus(source, reverse=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
                        return True
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    self.search_controller.show_search_result_context_menu(source)
                    return True
                if self.search_controller.handle_quick_search_keypress(source, event):
                    return True

        if isinstance(source, (QPushButton, QToolButton)) and event.type() == QEvent.Type.KeyPress:
            if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                if isinstance(source, QToolButton) and source.menu() is not None:
                    source.showMenu()
                else:
                    source.click()
                return True

        if table_widget is not None and source is table_widget.viewport():
            if event.type() == QEvent.Type.MouseMove:
                item = table_widget.itemAt(event.position().toPoint())
                if item and item.column() != 4:
                    self.presentation_controller.schedule_hover_popup(
                        {
                            "type": "preview",
                            "entry_id": str(item.data(Qt.ItemDataRole.UserRole)),
                            "global_pos": event.globalPosition().toPoint(),
                        }
                    )
                else:
                    self.presentation_controller.cancel_hover_popup()
            elif event.type() in {
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
                QEvent.Type.Wheel,
            }:
                self.presentation_controller.cancel_hover_popup()
        elif self.move_drag_widget(source) and self.window_bar_removed:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.start_move_window_drag(event.globalPosition().toPoint())
                return True
            if event.type() == QEvent.Type.MouseMove and self.dragging_frameless_window:
                if self.isMaximized():
                    return True
                self.move(event.globalPosition().toPoint() - self.frameless_drag_offset)
                return True
            if event.type() in {QEvent.Type.MouseButtonRelease, QEvent.Type.Leave}:
                self.finish_move_window_drag()
        elif source in self.action_hints:
            if event.type() == QEvent.Type.Enter:
                widget = source
                self.presentation_controller.schedule_hover_popup(
                    {
                        "type": "hint",
                        "text": self.action_hints[widget],
                        "global_pos": widget.mapToGlobal(widget.rect().bottomRight()),
                    }
                )
            elif event.type() in {
                QEvent.Type.Leave,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonDblClick,
            }:
                self.presentation_controller.cancel_hover_popup()

        return super().eventFilter(source, event)

    def update_search_results(self: "NoteCopyPaster") -> None:
        self.search_controller.update_search_results()

    def command_search_score(
        self: "NoteCopyPaster",
        entry: SnipcomEntry,
        query_casefold: str,
        content: str,
        *,
        usage_count: int = 0,
        transition_weight: int = 0,
    ) -> int:
        return self.search_controller.command_search_score(
            entry,
            query_casefold,
            content,
            usage_count=usage_count,
            transition_weight=transition_weight,
        )

    def clear_search_inline_ai_state(self: "NoteCopyPaster") -> None:
        self.search_inline_ai_timer.stop()
        self.search_inline_ai_request = ""
        self.search_inline_ai_suggestion = None
        self.search_inline_ai_error = ""
        self.search_inline_ai_busy = False

    def resizeEvent(self: "NoteCopyPaster", event) -> None:
        super().resizeEvent(event)
        self.update_background_pixmap()
        self.sync_table_columns_to_viewport()
        self.update_resize_grips()
        if self.toast_label.isVisible():
            x = max(12, self.width() - self.toast_label.width() - 16)
            y = max(12, self.height() - self.toast_label.height() - 16)
            self.toast_label.move(x, y)
        if self.instruction_banner.isVisible():
            x = max(16, (self.width() - self.instruction_banner.width()) // 2)
            y = max(16, (self.height() - self.instruction_banner.height()) // 2)
            self.instruction_banner.move(x, y)
        if self.terminal_ai_overlay.isVisible():
            self.presentation_controller.position_terminal_ai_overlay()

    def showEvent(self: "NoteCopyPaster", event) -> None:
        super().showEvent(event)
        self.apply_default_column_widths()
        self.update_tag_header_filter_button()
        self.update_resize_grips()

    def closeEvent(self: "NoteCopyPaster", event) -> None:
        self.save_runtime_preferences()
        self.linked_terminal_timer.stop()
        if self.store_window is not None:
            self.store_window.close()
        close_all_linked_terminal_sessions(linked_terminal_root_dir())
        super().closeEvent(event)
