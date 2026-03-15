from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

COLUMN_LABELS: dict[str, str] = {
    "name": "File name",
    "description": "Description",
    "tag": "Tag",
    "family": "Family",
    "modified": "Modified",
    "actions": "Actions",
}

from ..widgets import GridFileCard

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster
    from ...core.repository import SnipcomEntry


class ViewController:
    def __init__(self, window: "NoteCopyPaster") -> None:
        self.window = window

    def auto_refresh(self) -> None:
        from PyQt6.QtWidgets import QApplication
        if QApplication.activePopupWidget() is not None:
            return
        window = self.window
        scrollbar = window.table.verticalScrollBar()
        scroll_pos = scrollbar.value()
        selected_ids = {
            str(window.table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole))
            for index in window.table.selectedIndexes()
            if window.table.item(index.row(), 0)
        }
        self.refresh_table()
        scrollbar.setValue(scroll_pos)
        if selected_ids:
            for row in range(window.table.rowCount()):
                item = window.table.item(row, 0)
                if item and str(item.data(Qt.ItemDataRole.UserRole)) in selected_ids:
                    window.table.selectRow(row)
                    break

    def _column_text(self, key: str, entry: "SnipcomEntry", window: "NoteCopyPaster") -> str:
        if key == "family":
            return window.family_label_for(entry)
        if key == "tag":
            return window.tag_for(entry)
        if key == "modified":
            return datetime.fromtimestamp(entry.modified_timestamp).strftime("%Y-%m-%d %H:%M")
        if key == "description":
            return window.description_for(entry)
        return ""

    def refresh_table(self) -> None:
        window = self.window
        entries = window.sorted_active_entries(window.filtered_active_entries())
        window.entries_by_id = {entry.entry_id: entry for entry in entries}
        window.action_hints = {
            window.background_button: window.background_button_hint,
            window.view_toggle_button: "Switch between table and grid views.",
        }
        columns = window.table_columns
        window.table.clearSpans()
        window.table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            tag_accent = window.entry_tag_color(entry)
            if entry.dangerous:
                row_color: QColor | None = QColor(255, 188, 104)
            elif tag_accent:
                accent = QColor(tag_accent)
                row_color = accent.lighter(118) if accent.isValid() else None
            else:
                row_color = None

            for col, key in enumerate(columns):
                if key == "actions":
                    window.table.setCellWidget(row, col, self.build_actions_widget(entry))
                    continue

                item = QTableWidgetItem("" if key == "name" else self._column_text(key, entry, window))
                item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if row_color is not None:
                    item.setForeground(row_color)
                window.table.setItem(row, col, item)
                if key == "name":
                    window.table.setCellWidget(row, col, self.build_name_widget(entry))

        window.table.resizeRowsToContents()
        self.normalize_row_heights()
        window.table.horizontalHeader().setSortIndicator(window.sort_column, window.sort_order)
        window.update_grid_sort_buttons()
        window.filter_controller.rebuild_grid_tag_filter_menu()
        window.filter_controller.rebuild_main_family_filter_menu()
        self.refresh_grid_view()
        window.apply_default_column_widths()
        window.show_status(f"{len(entries)} active item(s), {window.repository.trash_count()} item(s) in trash.")

    def build_name_widget(self, entry: "SnipcomEntry") -> QWidget:
        window = self.window
        entry_color = window.entry_tag_color(entry)
        container = QWidget()
        container.setObjectName("entry-name-container")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        allow_folder_selection_toggle = window.folder_add_mode_active() and window.is_add_to_folder_candidate(entry)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not entry.is_folder and not allow_folder_selection_toggle)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(
            window.scaled_size(10),
            window.scaled_size(4),
            window.scaled_size(6),
            window.scaled_size(4),
        )
        layout.setSpacing(window.scaled_size(3))

        if window.folder_add_mode_active() and window.is_add_to_folder_candidate(entry):
            add_checkbox = QCheckBox("Select")
            add_checkbox.setChecked(window.is_add_to_folder_selected(entry))
            add_checkbox.toggled.connect(lambda checked: window.set_add_to_folder_selected(entry, checked))
            add_checkbox.setStyleSheet("QCheckBox { color: rgba(220, 226, 232, 0.92); padding: 0; }")
            window.apply_widget_zoom(add_checkbox, 8)
            layout.addWidget(add_checkbox, 0, Qt.AlignmentFlag.AlignLeft)

        badge_text = window.family_badge_text_for(entry)
        if badge_text:
            badge_label = QLabel(badge_text)
            badge_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            badge_label.setStyleSheet(
                "background-color: rgba(255, 255, 255, 28);"
                "color: #d8e3f0;"
                f"border-radius: {window.scaled_size(8)}px;"
                f"padding: {window.scaled_size(1)}px {window.scaled_size(7)}px;"
            )
            window.apply_widget_zoom(badge_label, 8)
            layout.addWidget(badge_label, 0, Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel(window.primary_text_for(entry))
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_label.setWordWrap(True)
        title_color = "#ffd7af" if entry.dangerous else (entry_color or "#f0f0f0")
        title_label.setStyleSheet(f"color: {title_color};")
        window.apply_widget_zoom(title_label, 10)
        layout.addWidget(title_label)


        if not entry.dangerous and entry_color:
            layout.setContentsMargins(
                window.scaled_size(8),
                window.scaled_size(4),
                window.scaled_size(6),
                window.scaled_size(4),
            )
            container.setStyleSheet(
                "#entry-name-container { "
                f"border-left: {window.scaled_size(2)}px solid {entry_color};"
                " }"
            )

        return container

    def build_actions_widget(self, entry: "SnipcomEntry") -> QWidget:
        window = self.window
        if window.folder_add_mode_active() and not entry.is_folder:
            widget = QWidget()
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            widget.setStyleSheet("background: transparent; border: none;")
            return widget
        if entry.is_folder:
            open_button = QPushButton("Open")
            open_button.clicked.connect(lambda: window.open_folder_entry(entry))
            window.style_action_button(open_button, compact=True)
            window.attach_action_hint(open_button, "Open this folder with its configured mode.")

            explorer_button = QPushButton("Open In Explorer")
            explorer_button.clicked.connect(lambda: window.open_folder_entry(entry, force_edit=True))
            window.style_action_button(explorer_button, compact=True)
            window.attach_action_hint(explorer_button, "Open this folder in the system file manager to edit contents.")

            more_button = QToolButton()
            more_button.setText("More...")
            more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            window.style_action_button(more_button, compact=True)
            window.attach_action_hint(
                more_button,
                "Open folder actions like rename and folder-mode changes.",
            )
            more_button.setMenu(window.build_more_menu(entry, more_button))

            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(2)
            layout.addWidget(open_button)
            layout.addWidget(explorer_button)
            layout.addWidget(more_button)

            widget = QWidget()
            widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            widget.setStyleSheet("background: transparent; border: none;")
            widget.setLayout(layout)
            return widget

        launch_button = QPushButton("Launch")
        launch_button.clicked.connect(lambda: window.launch_file_content(entry))
        window.style_action_button(launch_button, compact=True)
        window.attach_action_hint(launch_button, "Launch this entry content as a terminal command.")

        copy_button = QPushButton("Copy")
        copy_button.clicked.connect(lambda: window.copy_content(entry))
        window.style_action_button(copy_button, compact=True)
        window.attach_action_hint(copy_button, "Copy the content of this entry into the clipboard.")

        paste_button = QToolButton()
        paste_button.setText("Paste")
        paste_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        paste_button.setMenu(window.build_paste_menu(entry, paste_button))
        window.style_action_button(paste_button, compact=True)
        window.attach_action_hint(paste_button, "Open clipboard paste actions for this entry.")

        more_button = QToolButton()
        more_button.setText("More...")
        more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        window.style_action_button(more_button, compact=True)
        window.attach_action_hint(
            more_button,
            "Open more actions for this entry, including rename and tag editing.",
        )
        more_button.setMenu(window.build_more_menu(entry, more_button))

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(launch_button)
        layout.addWidget(copy_button)
        layout.addWidget(paste_button)
        layout.addWidget(more_button)

        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        widget.setStyleSheet("background: transparent; border: none;")
        widget.setLayout(layout)
        return widget

    def normalize_row_heights(self) -> None:
        window = self.window
        columns = getattr(window, "table_columns", ["name", "family", "tag", "modified", "actions"])
        actions_col = columns.index("actions") if "actions" in columns else None
        minimum_height = window.table.verticalHeader().minimumSectionSize()
        for row in range(window.table.rowCount()):
            desired_height = minimum_height
            if actions_col is not None:
                action_widget = window.table.cellWidget(row, actions_col)
                if action_widget is not None:
                    desired_height = max(desired_height, action_widget.sizeHint().height() + window.scaled_size(8))
            window.table.setRowHeight(row, desired_height)

    def clear_grid_layout(self) -> None:
        window = self.window
        while window.grid_layout.count():
            item = window.grid_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_grid_view(self) -> None:
        window = self.window
        self.clear_grid_layout()
        window.grid_cards = {}
        entries = window.sorted_active_entries(window.filtered_active_entries())
        for entry in entries:
            card = GridFileCard(window, entry)
            window.grid_cards[entry.entry_id] = card
            window.grid_layout.addWidget(card)
        window.filter_controller.rebuild_grid_tag_filter_menu()

    def handle_header_click(self, section: int) -> None:
        columns = self.window.table_columns
        if section < len(columns) and columns[section] == "actions":
            return
        self.window.set_sort_column(section)

    def show_table_context_menu(self, position: QPoint) -> None:
        window = self.window
        row = window.table.rowAt(position.y())
        if row < 0:
            return
        item = window.table.item(row, 0)
        if item is None:
            return
        entry_id = str(item.data(Qt.ItemDataRole.UserRole))
        entry = window.entry_for(entry_id)
        if entry is None:
            return
        window.table.selectRow(row)
        menu = window.build_more_menu(
            entry,
            window.table,
            include_open_action=not entry.is_folder,
            include_paste_actions=not entry.is_folder,
        )
        menu.exec(window.table.viewport().mapToGlobal(position))

    def show_header_context_menu(self, pos: QPoint) -> None:
        window = self.window
        header = window.table.horizontalHeader()
        visual = header.visualIndexAt(pos.x())
        if visual < 0:
            return
        logical = header.logicalIndex(visual)
        columns = window.table_columns
        if logical < 0 or logical >= len(columns):
            return
        current_key = columns[logical]

        menu = QMenu(header)

        change_menu = menu.addMenu("Change to")
        for key, label in COLUMN_LABELS.items():
            action = change_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(key == current_key)
            action.triggered.connect(lambda _, k=key, lc=logical: self._set_column_key(lc, k))

        menu.addSeparator()
        delete_action = menu.addAction("Delete column")
        delete_action.setEnabled(len(columns) > 1)
        delete_action.triggered.connect(lambda: self._delete_column(logical))

        new_menu = menu.addMenu("New column")
        for key, label in COLUMN_LABELS.items():
            action = new_menu.addAction(label)
            action.triggered.connect(lambda _, k=key, lc=logical: self._insert_column(lc + 1, k))

        menu.exec(header.viewport().mapToGlobal(pos))

    def _rebuild_table_columns(self) -> None:
        window = self.window
        columns = window.table_columns
        header = window.table.horizontalHeader()
        header.blockSignals(True)
        window.table.setColumnCount(len(columns))
        window.table.setHorizontalHeaderLabels([COLUMN_LABELS.get(k, k.title()) for k in columns])
        from PyQt6.QtWidgets import QHeaderView
        for col in range(len(columns)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.blockSignals(False)
        window.columns_initialized = False
        window.settings.pop("column_order", None)
        window.save_runtime_preferences()
        self.refresh_table()

    def _set_column_key(self, logical: int, key: str) -> None:
        window = self.window
        if logical < 0 or logical >= len(window.table_columns):
            return
        window.table_columns[logical] = key
        self._rebuild_table_columns()

    def _delete_column(self, logical: int) -> None:
        window = self.window
        if len(window.table_columns) <= 1:
            return
        if logical < 0 or logical >= len(window.table_columns):
            return
        window.table_columns.pop(logical)
        self._rebuild_table_columns()

    def _insert_column(self, after_logical: int, key: str) -> None:
        window = self.window
        insert_at = max(0, min(after_logical, len(window.table_columns)))
        window.table_columns.insert(insert_at, key)
        self._rebuild_table_columns()

    def handle_cell_double_click(self, row: int, column: int) -> None:
        window = self.window
        entry = self.entry_for_row(row)
        if entry is None:
            return
        if column == 0:
            window.open_file(entry)
        elif column == 1 and not entry.is_folder:
            window.modify_tag(entry)

    def entry_for_row(self, row: int) -> "SnipcomEntry | None":
        item = self.window.table.item(row, 0)
        if item is None:
            return None
        entry_id = str(item.data(Qt.ItemDataRole.UserRole))
        return self.window.entry_for(entry_id)

    def focus_file(self, target: "SnipcomEntry | Path | str") -> None:
        window = self.window
        entry = window.entry_for(target)
        if entry is None:
            return
        if window.view_mode == "grid":
            card = window.grid_cards.get(entry.entry_id)
            if card is not None:
                window.grid_scroll.ensureWidgetVisible(card)
            return

        for row in range(window.table.rowCount()):
            item = window.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == entry.entry_id:
                window.table.setCurrentCell(row, 0)
                window.table.scrollToItem(item)
                break
