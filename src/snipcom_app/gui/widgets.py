from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster
    from ..core.repository import SnipcomEntry


class RoundedTableItemDelegate(QStyledItemDelegate):
    def __init__(self, manager: "NoteCopyPaster") -> None:
        super().__init__(manager)
        self.manager = manager

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(option.rect.adjusted(1, 3, -1, -3))
        radius = min(10.0, rect.height() / 2.0)
        column = index.column()
        last_column = index.model().columnCount() - 1

        use_background = bool(self.manager.background_path)
        if option.state & QStyle.StateFlag.State_Selected:
            background = QColor(44, 52, 62, 208 if use_background else 255)
            text_color = QColor(246, 246, 246)
            border_color = QColor(166, 182, 198, 110)
        else:
            if use_background:
                background = QColor(20, 24, 28, 134)
                border_color = QColor(255, 255, 255, 36)
            else:
                background = QColor(43, 48, 55)
                border_color = QColor(90, 100, 112, 90)
            text_color = QColor(236, 236, 236)

        if column == 0:
            first_rect = self.manager.table.visualRect(index)
            last_index = index.siblingAtColumn(last_column)
            last_rect = self.manager.table.visualRect(last_index)
            full_row_rect = QRectF(
                first_rect.left() + 1,
                first_rect.top() + 4,
                max(0, last_rect.right() - first_rect.left() - 1),
                max(0, first_rect.height() - 8),
            )
            full_path = QPainterPath()
            full_path.addRoundedRect(full_row_rect, radius, radius)
            painter.fillPath(full_path, background)
            painter.setPen(border_color)
            painter.drawPath(full_path)

        if column != last_column:
            if self.manager.table.cellWidget(index.row(), column) is not None:
                painter.restore()
                return
            text_rect = option.rect.adjusted(14, 0, -10, 0)
            painter.setPen(text_color)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                str(index.data() or ""),
            )

        painter.restore()


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 10) -> None:
        super().__init__(parent)
        self.item_list: list[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self.item_list.append(item)

    def count(self) -> int:
        return len(self.item_list)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self.do_layout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self.item_list:
            spacing = self.spacing()
            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y += line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


class PopupFolderTile(QFrame):
    def __init__(self, manager: "NoteCopyPaster", entry: "SnipcomEntry") -> None:
        super().__init__()
        self.manager = manager
        self.entry = entry
        self.popup_menu = None  # set externally by build_popup_folder_tile
        self.setObjectName("popup-folder-tile")
        self.setFixedSize(manager.scaled_size(150), manager.scaled_size(108))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "#popup-folder-tile {"
            "background: rgba(24, 28, 34, 178);"
            "border: 1px solid rgba(255, 255, 255, 34);"
            "border-radius: 10px;"
            "}"
            "#popup-folder-tile:hover {"
            "background: rgba(34, 40, 48, 212);"
            "border-color: rgba(255, 255, 255, 58);"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            manager.scaled_size(10),
            manager.scaled_size(10),
            manager.scaled_size(10),
            manager.scaled_size(10),
        )
        layout.setSpacing(manager.scaled_size(6))

        kind_label = QLabel("Folder" if entry.is_folder else "File")
        kind_label.setStyleSheet("color: rgba(214, 222, 230, 0.72);")
        manager.apply_widget_zoom(kind_label, 8)
        layout.addWidget(kind_label)

        name_label = QLabel(entry.display_name)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #edf1f4;")
        manager.apply_widget_zoom(name_label, 9)
        layout.addWidget(name_label, 1)

        # Hover overlay — same structure as GridFileCard
        self.overlay = QWidget(self)
        self.overlay.hide()
        self.overlay.setStyleSheet(
            "background-color: rgba(18, 18, 22, 190);"
            "border: 1px solid rgba(255, 255, 255, 50);"
            "border-radius: 10px;"
        )

        if entry.is_folder:
            open_button = QPushButton("Open", self.overlay)
            open_button.clicked.connect(lambda: self._act(lambda: manager.open_folder_entry(self.entry)))
            manager.style_grid_overlay_button(open_button)
            manager.attach_action_hint(open_button, "Open this folder with its configured mode.")

            more_button = QToolButton(self.overlay)
            more_button.setText("More...")
            more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            manager.style_grid_overlay_button(more_button)
            manager.attach_action_hint(more_button, "Open folder actions.")
            more_menu = manager.build_more_menu(self.entry, more_button, include_open_action=False, include_paste_actions=False)
            more_menu.triggered.connect(lambda *_: self._act(lambda: None))
            more_button.setMenu(more_menu)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(0)
            top_row.addWidget(open_button)

            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(0)
            bottom_row.addWidget(more_button)
        else:
            launch_button = QPushButton("Launch", self.overlay)
            launch_button.clicked.connect(lambda: self._act(lambda: manager.launch_file_content(self.entry)))
            manager.style_grid_overlay_button(launch_button, right_divider=True)
            manager.attach_action_hint(launch_button, "Launch this entry content as a terminal command.")

            copy_button = QPushButton("Copy", self.overlay)
            copy_button.clicked.connect(lambda: self._act(lambda: manager.copy_content(self.entry)))
            manager.style_grid_overlay_button(copy_button)
            manager.attach_action_hint(copy_button, "Copy the content of this entry into the clipboard.")

            more_button = QToolButton(self.overlay)
            more_button.setText("More...")
            more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            manager.style_grid_overlay_button(more_button)
            manager.attach_action_hint(more_button, "Open more actions for this entry.")
            more_menu = manager.build_more_menu(self.entry, more_button, include_open_action=True, include_paste_actions=True)
            more_menu.triggered.connect(lambda *_: self._act(lambda: None))
            more_button.setMenu(more_menu)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(0)
            top_row.addWidget(launch_button)

            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(0)
            bottom_row.addWidget(copy_button)
            bottom_row.addWidget(more_button)

        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)
        overlay_layout.addLayout(top_row, 7)
        overlay_layout.addLayout(bottom_row, 3)

    def _act(self, fn) -> None:
        """Execute fn then close the parent folder popup."""
        fn()
        pm = self.popup_menu
        if pm is not None and not pm.isHidden():
            pm.close()

    def enterEvent(self, event) -> None:
        self.overlay.show()
        self.overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())

    def contextMenuEvent(self, event) -> None:
        self.manager.show_popup_folder_tile_context_menu(self.entry, self, event.globalPos())
        event.accept()


class GridFileCard(QFrame):
    def __init__(self, manager: "NoteCopyPaster", entry: "SnipcomEntry") -> None:
        super().__init__()
        self.manager = manager
        self.entry = entry
        self.setObjectName("grid-file-card")
        self.setFixedSize(manager.scaled_size(184), manager.scaled_size(184))
        self.setFrameShape(QFrame.Shape.NoFrame)
        entry_accent_color = QColor(manager.entry_tag_color(entry))
        has_accent = entry_accent_color.isValid() and not entry.dangerous
        border_color = "rgba(255, 197, 122, 120)"
        background_color = "rgba(42, 26, 24, 166)"
        if not entry.dangerous:
            if has_accent:
                border_color = f"rgba({entry_accent_color.red()}, {entry_accent_color.green()}, {entry_accent_color.blue()}, 136)"
                background_color = (
                    f"rgba({max(16, entry_accent_color.red() // 5)}, "
                    f"{max(20, entry_accent_color.green() // 5)}, "
                    f"{max(24, entry_accent_color.blue() // 5)}, 168)"
                )
            else:
                border_color = "rgba(255, 255, 255, 36)"
                background_color = "rgba(24, 28, 34, 150)"
        self.setStyleSheet(
            "#grid-file-card {"
            f"background-color: {background_color};"
            f"border: 1px solid {border_color};"
            "border-radius: 10px;"
            "}"
        )

        icon_label = QLabel()
        icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_DirIcon if entry.is_folder else QStyle.StandardPixmap.SP_FileIcon
        )
        icon_size = manager.scaled_size(52)
        icon_label.setPixmap(icon.pixmap(icon_size, icon_size))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tag_row = QWidget()
        tag_row_layout = QHBoxLayout(tag_row)
        tag_row_layout.setContentsMargins(0, 0, 0, 0)
        tag_row_layout.setSpacing(manager.scaled_size(6))

        if manager.folder_add_mode_active() and manager.is_add_to_folder_candidate(entry):
            select_checkbox = QCheckBox("Select")
            select_checkbox.setChecked(manager.is_add_to_folder_selected(entry))
            select_checkbox.toggled.connect(lambda checked: manager.set_add_to_folder_selected(self.entry, checked))
            select_checkbox.setStyleSheet("QCheckBox { color: rgba(224, 230, 236, 0.9); }")
            manager.apply_widget_zoom(select_checkbox, 8)
            tag_row_layout.addWidget(select_checkbox, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        tag_text = manager.tag_for(entry)
        tag_label = QLabel(tag_text if tag_text else " ")
        tag_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        manager.apply_widget_zoom(tag_label, 9)
        tag_label.setStyleSheet(
            f"color: {'rgba(255, 214, 160, 0.96)' if entry.dangerous else (entry_accent_color.name() if has_accent else 'rgba(235, 235, 235, 0.88)')};"
            f"padding: 0 {manager.scaled_size(6)}px;"
        )
        tag_row_layout.addWidget(tag_label, 1)

        badge_text = manager.family_badge_text_for(entry)
        if badge_text:
            badge_label = QLabel(badge_text)
            manager.apply_widget_zoom(badge_label, 8)
            badge_label.setStyleSheet(
                "background-color: rgba(255, 255, 255, 28);"
                "color: #d8e3f0;"
                f"border-radius: {manager.scaled_size(8)}px;"
                f"padding: {manager.scaled_size(1)}px {manager.scaled_size(7)}px;"
            )
            tag_row_layout.addWidget(badge_label, 0, Qt.AlignmentFlag.AlignRight)

        name_label = QLabel(manager.primary_text_for(entry))
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setWordWrap(True)
        manager.apply_widget_zoom(name_label, 10)
        name_label.setStyleSheet(
            f"color: {'#ffd7af' if entry.dangerous else (entry_accent_color.name() if has_accent else '#f0f0f0')};"
            f"padding: 0 {manager.scaled_size(8)}px {manager.scaled_size(8)}px {manager.scaled_size(8)}px;"
        )

        subtitle_text = manager.secondary_text_for(entry)
        subtitle_label = QLabel(subtitle_text if subtitle_text else " ")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)
        manager.apply_widget_zoom(subtitle_label, 8)
        subtitle_label.setStyleSheet(
            f"color: {'rgba(255, 226, 195, 0.82)' if entry.dangerous else 'rgba(216, 222, 228, 0.72)'};"
            f"padding: 0 {manager.scaled_size(10)}px {manager.scaled_size(4)}px {manager.scaled_size(10)}px;"
        )

        base_layout = QVBoxLayout(self)
        base_layout.setContentsMargins(
            manager.scaled_size(10),
            manager.scaled_size(10),
            manager.scaled_size(10),
            manager.scaled_size(10),
        )
        base_layout.setSpacing(manager.scaled_size(8))
        base_layout.addWidget(tag_row)
        base_layout.addStretch()
        base_layout.addWidget(icon_label)
        base_layout.addWidget(name_label)
        base_layout.addWidget(subtitle_label)
        base_layout.addStretch()

        self.overlay = QWidget(self)
        self.overlay.hide()
        self.overlay.setStyleSheet(
            f"background-color: {'rgba(42, 22, 18, 204)' if entry.dangerous else 'rgba(18, 18, 22, 190)'};"
            f"border: 1px solid {'rgba(255, 197, 122, 132)' if entry.dangerous else 'rgba(255, 255, 255, 50)'};"
            "border-radius: 10px;"
        )

        if entry.is_folder:
            open_button = QPushButton("Open", self.overlay)
            open_button.clicked.connect(lambda: self.manager.open_folder_entry(self.entry))
            self.manager.style_grid_overlay_button(open_button)
            self.manager.attach_action_hint(open_button, "Open this folder with its configured mode.")

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(0)
            top_row.addWidget(open_button)

            more_button = QToolButton(self.overlay)
            more_button.setText("More...")
            more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.manager.style_grid_overlay_button(more_button)
            self.manager.attach_action_hint(more_button, "Open folder actions.")
            more_button.setMenu(
                self.manager.build_more_menu(
                    self.entry,
                    more_button,
                    include_open_action=False,
                    include_paste_actions=False,
                )
            )

            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(0)
            bottom_row.addWidget(more_button)
        else:
            launch_button = QPushButton("Launch", self.overlay)
            launch_button.clicked.connect(lambda: self.manager.launch_file_content(self.entry))
            self.manager.style_grid_overlay_button(launch_button, right_divider=True)
            self.manager.attach_action_hint(launch_button, "Launch this entry content as a terminal command.")

            copy_button = QPushButton("Copy", self.overlay)
            copy_button.clicked.connect(lambda: self.manager.copy_content(self.entry))
            self.manager.style_grid_overlay_button(copy_button)
            self.manager.attach_action_hint(copy_button, "Copy the content of this entry into the clipboard.")

            more_button = QToolButton(self.overlay)
            more_button.setText("More...")
            more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.manager.style_grid_overlay_button(more_button)
            self.manager.attach_action_hint(more_button, "Open more actions for this entry.")
            more_button.setMenu(
                self.manager.build_more_menu(
                    self.entry,
                    more_button,
                    include_open_action=True,
                    include_paste_actions=True,
                )
            )

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(0)
            top_row.addWidget(launch_button)

            bottom_row = QHBoxLayout()
            bottom_row.setContentsMargins(0, 0, 0, 0)
            bottom_row.setSpacing(0)
            bottom_row.addWidget(copy_button)
            bottom_row.addWidget(more_button)

        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)
        overlay_layout.addLayout(top_row, 7)
        overlay_layout.addLayout(bottom_row, 3)

    def enterEvent(self, event) -> None:
        if not self.manager.folder_add_mode_active():
            self.overlay.show()
            self.overlay.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.overlay.hide()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
