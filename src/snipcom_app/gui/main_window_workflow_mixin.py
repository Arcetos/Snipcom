from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..integration.desktop_integration import launch_in_terminal as launch_in_terminal_with_fallback
from ..integration.desktop_integration import open_path_with_fallback as open_path_with_fallback_service
from ..core.helpers import available_path
from ..core.repository import SnipcomEntry
from .widgets import FlowLayout, PopupFolderTile
from .workflow import workflow_folder_popup
from .workflow import workflow_entry_actions
from .workflow import workflow_entry_content
from .workflow import workflow_terminal_actions
from .main_window_trash_mixin import MainWindowTrashMixin

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowWorkflowMixin(MainWindowTrashMixin):
    def selected_entries(self: "NoteCopyPaster") -> list[SnipcomEntry]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        entries: list[SnipcomEntry] = []
        for row in rows:
            entry = self.view_controller.entry_for_row(row)
            if entry is not None:
                entries.append(entry)
        return entries

    def selected_paths(self: "NoteCopyPaster") -> list[Path]:
        return [entry.path for entry in self.selected_entries() if entry.is_file and entry.path is not None]

    def active_entries(self: "NoteCopyPaster") -> list[SnipcomEntry]:
        return self.repository.active_entries(self.tags, self.snip_types)

    def active_files(self: "NoteCopyPaster") -> list[Path]:
        return [entry.path for entry in self.active_entries() if entry.is_file and entry.path is not None]

    def trash_files(self: "NoteCopyPaster") -> list[Path]:
        return self.repository.trash_files()

    def sorted_active_entries(self: "NoteCopyPaster", entries: list[SnipcomEntry] | None = None) -> list[SnipcomEntry]:
        entries = list(entries or self.active_entries())

        def sort_key(entry: SnipcomEntry) -> tuple:
            if self.sort_column == 0:
                return (entry.display_name.casefold(), entry.entry_id)
            if self.sort_column == 1:
                return (self.family_label_for(entry).casefold(), entry.display_name.casefold())
            if self.sort_column == 2:
                return (",".join(tag.casefold() for tag in self.tags_for(entry)), entry.display_name.casefold())
            if self.sort_column == 3:
                return (entry.modified_timestamp, entry.display_name.casefold())
            return (entry.display_name.casefold(), entry.entry_id)

        entries.sort(key=sort_key, reverse=self.sort_order == Qt.SortOrder.DescendingOrder)
        return entries

    def workflow_scope_entries(self: "NoteCopyPaster") -> list[SnipcomEntry]:
        return self.active_entries()

    def filtered_active_entries(self: "NoteCopyPaster") -> list[SnipcomEntry]:
        entries = self.workflow_scope_entries()
        if self.selected_family_filter:
            entries = [
                entry
                for entry in entries
                if (
                    entry.is_command and entry.family_key == self.selected_family_filter
                )
                or (
                    entry.is_file and self.selected_family_filter in self.tags_for(entry)
                )
            ]
        if self.selected_grid_tags:
            entries = [entry for entry in entries if any(tag in self.selected_grid_tags for tag in self.tags_for(entry))]
        return entries

    def refresh_table(self: "NoteCopyPaster") -> None:
        self.view_controller.refresh_table()

    def refresh_workflow_views(
        self: "NoteCopyPaster",
        *,
        refresh_search: bool = True,
        refresh_store: bool = False,
    ) -> None:
        self.view_controller.refresh_table()
        if refresh_search:
            self.search_controller.update_search_results()
        if refresh_store and self.store_window is not None:
            self.store_window.refresh_entries()

    def _open_workspace_path(self: "NoteCopyPaster", path: Path, *, failure_title: str) -> bool:
        if self.open_path_with_fallback(
            path,
            "folder_opener_executable",
            "Choose folder opener",
            failure_title,
        ):
            return True
        QMessageBox.warning(self, failure_title, f"Could not open {path}.")
        return False

    def grid_filtered_entries(self: "NoteCopyPaster") -> list[SnipcomEntry]:
        return self.filtered_active_entries()

    def create_new_file(self: "NoteCopyPaster") -> None:
        self.workflow_controller.create_new_file()

    def create_new_folder(self: "NoteCopyPaster") -> None:
        self.workflow_controller.create_new_folder()

    def open_folder(self: "NoteCopyPaster") -> None:
        workflow_folder_popup.open_folder(self)

    def open_folder_entry(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, *, force_edit: bool = False) -> None:
        workflow_folder_popup.open_folder_entry(self, target, force_edit=force_edit)

    def close_active_folder_popup(self: "NoteCopyPaster") -> None:
        workflow_folder_popup.close_active_folder_popup(self)

    def show_popup_folder_contents(self: "NoteCopyPaster", folder_entry: SnipcomEntry, *, edit_mode: bool = False) -> None:
        workflow_folder_popup.show_popup_folder_contents(self, folder_entry, edit_mode=edit_mode)

    def configure_popup_folder_button(self: "NoteCopyPaster", text: str) -> QPushButton:
        return workflow_folder_popup.configure_popup_folder_button(self, text)

    def _apply_folder_edit_selection(
        self: "NoteCopyPaster",
        folder_entry: SnipcomEntry,
        selection_list: QListWidget | None,
        *,
        action: str,
        popup_menu: QMenu,
    ) -> None:
        workflow_folder_popup.apply_folder_edit_selection(
            self,
            folder_entry,
            selection_list,
            action=action,
            popup_menu=popup_menu,
        )

    def build_popup_folder_tile(self: "NoteCopyPaster", entry: SnipcomEntry, popup_menu: QMenu) -> QWidget:
        return workflow_folder_popup.build_popup_folder_tile(self, entry, popup_menu)

    def open_popup_folder_tile_actions(self: "NoteCopyPaster", entry: SnipcomEntry, anchor: QWidget) -> None:
        workflow_folder_popup.open_popup_folder_tile_actions(self, entry, anchor)

    def show_popup_folder_tile_context_menu(
        self: "NoteCopyPaster",
        entry: SnipcomEntry,
        anchor: QWidget,
        global_pos: QPoint,
    ) -> None:
        workflow_folder_popup.show_popup_folder_tile_context_menu(self, entry, anchor, global_pos)

    def _open_popup_folder_in_explorer(self: "NoteCopyPaster", folder_entry: SnipcomEntry) -> None:
        workflow_folder_popup.open_popup_folder_in_explorer(self, folder_entry)

    def reset_defaults(self: "NoteCopyPaster") -> None:
        reply = QMessageBox.question(
            self,
            "Reset defaults",
            "Reset window size, view mode, zoom, sorting, filters, columns, and background image to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        preserved_settings = {
            key: self.settings[key]
            for key in ("texts_dir", "terminal_executable", "folder_opener_executable")
            if key in self.settings
        }
        self.settings = preserved_settings
        self.launch_options = {}
        self.background_path = ""
        self.columns_initialized = False
        self.view_mode = "table"
        self.add_to_folder_target_id = ""
        self.add_to_folder_selected_ids.clear()
        self._update_add_to_folder_controls()
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.apply_window_bar_setting(False)
        self.selected_grid_tags.clear()
        self.selected_family_filter = ""
        self.table_zoom_percent = 100
        self.grid_zoom_percent = 100
        self.search_input.clear()
        self.resize(812, 560)
        self.restore_default_column_order()
        self.view_stack.setCurrentWidget(self.table_page)
        self.update_view_toggle_button()
        self.apply_background()
        self.sync_zoom_slider_to_view()
        self.apply_zoom()
        self.refresh_table()
        self.save_runtime_preferences()
        self.save_launch_options()
        self.show_feedback("Defaults restored.")

    def open_store_page(self: "NoteCopyPaster") -> None:
        if self.store_window is None:
            self.show_toast("Store window is not available yet.")
            return
        self.store_window.show()
        self.store_window.raise_()
        self.store_window.activateWindow()

    def choose_terminal_executable(self: "NoteCopyPaster", parent: QWidget | None = None) -> str | None:
        terminal_path, _ = QFileDialog.getOpenFileName(
            parent or self,
            "Choose terminal application",
            "/usr/bin",
            "Applications (*)",
        )
        if not terminal_path:
            return None
        self.settings["terminal_executable"] = terminal_path
        self.save_settings()
        return terminal_path

    def launch_in_terminal(self: "NoteCopyPaster", command: str, keep_open: bool) -> bool:
        launched = launch_in_terminal_with_fallback(
            self.settings,
            command,
            keep_open,
            chooser=lambda: self.choose_terminal_executable(),
        )
        if not launched:
            selected_terminal = str(self.settings.get("terminal_executable", "")).strip()
            if selected_terminal:
                QMessageBox.warning(self, "Launch failed", "The selected terminal application could not launch the command.")
        return launched

    def choose_opener_executable(
        self: "NoteCopyPaster",
        setting_key: str,
        title: str,
        parent: QWidget | None = None,
    ) -> str | None:
        opener_path, _ = QFileDialog.getOpenFileName(
            parent or self,
            title,
            "/usr/bin",
            "Applications (*)",
        )
        if not opener_path:
            return None
        self.settings[setting_key] = opener_path
        self.save_settings()
        return opener_path

    def open_path_with_fallback(
        self: "NoteCopyPaster",
        path: Path,
        setting_key: str,
        chooser_title: str,
        failure_title: str,
    ) -> bool:
        opened = open_path_with_fallback_service(
            self.settings,
            path,
            setting_key,
            chooser=lambda: self.choose_opener_executable(setting_key, chooser_title),
        )
        if not opened and str(self.settings.get(setting_key, "")).strip():
            QMessageBox.warning(self, failure_title, "The selected opener application could not open this path.")
        return opened

    def edit_launch_options(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.edit_launch_options(self, target)

    def open_command_editor(self: "NoteCopyPaster", entry: SnipcomEntry) -> None:
        workflow_entry_content.open_command_editor(self, entry)

    def open_file(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.open_file(self, target)

    def read_file_text(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, action_name: str) -> str | None:
        return workflow_entry_content.read_file_text(self, target, action_name)

    def read_entry_text_quiet(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str | None:
        return workflow_entry_content.read_entry_text_quiet(self, target)

    def write_entry_text(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, content: str, action_name: str) -> bool:
        return workflow_entry_content.write_entry_text(self, target, content, action_name)

    def copy_content(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.copy_content(self, target)

    def paste_clipboard_content(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, position: str) -> None:
        workflow_entry_content.paste_clipboard_content(self, target, position)

    def prepend_paste(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.prepend_paste(self, target)

    def append_paste(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.append_paste(self, target)

    def rewrite_paste(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_content.rewrite_paste(self, target)

    def build_command_text(
        self: "NoteCopyPaster",
        target: SnipcomEntry | Path | str,
        action_name: str,
    ) -> tuple[str, dict[str, object]] | tuple[None, None]:
        return workflow_entry_content.build_command_text(self, target, action_name)

    def active_linked_terminal_sessions(self: "NoteCopyPaster") -> list[dict[str, object]]:
        return workflow_terminal_actions.active_linked_terminal_sessions(self)

    def selected_linked_terminal_label(self: "NoteCopyPaster") -> str:
        return workflow_terminal_actions.selected_linked_terminal_label(self)

    def record_command_usage(
        self: "NoteCopyPaster",
        entry: SnipcomEntry,
        *,
        event_kind: str,
        terminal_label: str = "",
        track_transition: bool = False,
        context: dict[str, object] | None = None,
    ) -> None:
        workflow_terminal_actions.record_command_usage(
            self,
            entry,
            event_kind=event_kind,
            terminal_label=terminal_label,
            track_transition=track_transition,
            context=context,
        )

    def current_linked_terminal_session(self: "NoteCopyPaster") -> dict[str, object] | None:
        return workflow_terminal_actions.current_linked_terminal_session(self)

    def refresh_linked_terminal_toolbar(self: "NoteCopyPaster") -> None:
        self.terminal_controller.refresh_linked_terminal_toolbar()

    def open_linked_terminal(self: "NoteCopyPaster") -> None:
        self.terminal_controller.open_linked_terminal()

    def send_terminal_input_command(self: "NoteCopyPaster") -> None:
        self.terminal_controller.send_terminal_input_command()

    def copy_selected_terminal_output(self: "NoteCopyPaster") -> None:
        self.terminal_controller.copy_selected_terminal_output()

    def create_file_with_content(
        self: "NoteCopyPaster",
        file_name: str,
        content: str,
        *,
        open_after_create: bool = False,
    ) -> Path | None:
        return workflow_terminal_actions.create_file_with_content(
            self,
            file_name,
            content,
            open_after_create=open_after_create,
        )

    def save_selected_terminal_output_to_new_file(self: "NoteCopyPaster") -> None:
        self.terminal_controller.save_selected_terminal_output_to_new_file()

    def begin_append_selected_terminal_output(self: "NoteCopyPaster") -> None:
        self.terminal_controller.begin_append_selected_terminal_output()

    def cancel_append_output_selection(self: "NoteCopyPaster") -> None:
        workflow_terminal_actions.cancel_append_output_selection(self)

    def append_output_to_file(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_terminal_actions.append_output_to_file(self, target)

    def handle_send_command_button(
        self: "NoteCopyPaster",
        target: SnipcomEntry | Path | str,
        button: QWidget,
    ) -> None:
        workflow_terminal_actions.handle_send_command_button(self, target, button)

    def send_file_content(
        self: "NoteCopyPaster",
        target: SnipcomEntry | Path | str,
        session: Path | None = None,
        session_label: str | None = None,
    ) -> None:
        workflow_terminal_actions.send_file_content(
            self,
            target,
            session=session,
            session_label=session_label,
        )

    def launch_file_content(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_terminal_actions.launch_file_content(self, target)

    def rename_file(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.rename_file(self, target)

    def delete_folder_entry(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.delete_folder_entry(self, target)

    def modify_tag(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.modify_tag(self, target)

    def add_entry_to_favorites(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.add_entry_to_favorites(self, target)

    def remove_entry_from_favorites(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.remove_entry_from_favorites(self, target)

    def add_description(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.add_description(self, target)

    def toggle_dangerous(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        workflow_entry_actions.toggle_dangerous(self, target)

    def change_snip_type(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        self.workflow_controller.change_snip_type(target)

    def description_for(self: "NoteCopyPaster", entry: SnipcomEntry) -> str:
        if entry.is_file and entry.path is not None:
            return self.descriptions.get(self.repository.storage_key(entry.path), "")
        return ""

    def set_description(self: "NoteCopyPaster", entry: SnipcomEntry, desc: str) -> None:
        if entry.is_file and entry.path is not None:
            key = self.repository.storage_key(entry.path)
            if desc.strip():
                self.descriptions[key] = desc.strip()
            else:
                self.descriptions.pop(key, None)
            self.repository.save_descriptions(self.descriptions)
