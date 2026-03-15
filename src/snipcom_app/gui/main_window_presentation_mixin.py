from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtWidgets import QSizePolicy, QStyle, QToolButton, QWidget

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster
    from ..core.repository import SnipcomEntry


class MainWindowPresentationMixin:
    def show_status(self: "NoteCopyPaster", message: str) -> None:
        self.status_label.setText(message)

    def show_feedback(self: "NoteCopyPaster", message: str, *, timeout_ms: int = 2600) -> None:
        self.show_status(message)
        self.show_toast(message, timeout_ms=timeout_ms)

    def style_terminal_toolbar(self: "NoteCopyPaster") -> None:
        radius = self.scaled_size(10)
        padding_v = self.scaled_size(7)
        padding_h = self.scaled_size(10)
        self.terminal_toolbar_widget.setObjectName("terminal-toolbar")
        self.terminal_toolbar_widget.setStyleSheet(
            "#terminal-toolbar {"
            "background-color: rgba(12, 16, 20, 186);"
            "border: 1px solid rgba(255, 255, 255, 34);"
            f"border-radius: {radius}px;"
            "}"
        )
        self.terminal_selector_button.setStyleSheet(
            "QToolButton {"
            "background-color: rgba(28, 36, 44, 220);"
            "color: #f0f2f5;"
            "border: 1px solid rgba(255, 255, 255, 44);"
            f"border-radius: {radius}px;"
            f"padding: {padding_v}px {padding_h}px;"
            "}"
            "QToolButton:hover, QToolButton:focus {"
            "background-color: rgba(50, 64, 80, 230);"
            "border: 1px solid rgba(255, 255, 255, 84);"
            "}"
            "QToolButton::menu-indicator { subcontrol-position: right center; }"
        )
        self.terminal_command_input.setStyleSheet(
            "QLineEdit {"
            "background-color: rgba(22, 28, 34, 218);"
            "color: #f3f4f6;"
            "border: 1px solid rgba(255, 255, 255, 38);"
            f"border-radius: {radius}px;"
            f"padding: {padding_v}px {padding_h}px;"
            "}"
        )
        for button in (
            self.copy_terminal_output_button,
            self.save_terminal_output_button,
            self.append_terminal_output_button,
        ):
            font = button.font()
            font.setPointSize(max(7, self.scaled_size(10)))
            button.setFont(font)
            button.setStyleSheet(
                "QPushButton {"
                "background-color: rgba(52, 66, 82, 218);"
                "color: #f4f6f8;"
                "border: 1px solid rgba(255, 255, 255, 44);"
                f"border-radius: {radius}px;"
                f"padding: {padding_v}px {padding_h}px;"
                "}"
                "QPushButton:hover, QPushButton:focus {"
                "background-color: rgba(74, 92, 112, 230);"
                "border: 1px solid rgba(255, 255, 255, 84);"
                "}"
                "QPushButton:pressed { background-color: rgba(44, 56, 70, 236); }"
            )

    def apply_background(self: "NoteCopyPaster") -> None:
        if not self.background_path:
            self.background_label.clear()
            self.background_label.hide()
            self.apply_content_surface_styles(False)
            return

        background_path = Path(self.background_path)
        if not background_path.exists():
            self.background_path = ""
            self.settings.pop("background_path", None)
            self.save_settings()
            self.background_label.clear()
            self.background_label.hide()
            self.apply_content_surface_styles(False)
            return

        self.background_label.show()
        self.update_background_pixmap()
        self.apply_content_surface_styles(True)

    def update_background_pixmap(self: "NoteCopyPaster") -> None:
        if not self.background_path:
            self.background_label.clear()
            self.background_label.hide()
            return

        background_path = Path(self.background_path)
        if not background_path.exists():
            self.background_label.clear()
            self.background_label.hide()
            return

        area = self.centralWidget().rect()
        self.background_label.setGeometry(area)
        if area.width() <= 0 or area.height() <= 0:
            return

        from PyQt6.QtGui import QPixmap

        pixmap = QPixmap(str(background_path))
        if pixmap.isNull():
            self.background_label.clear()
            self.background_label.hide()
            return

        scaled = pixmap.scaled(
            area.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.background_label.setPixmap(scaled)
        self.background_label.show()
        self.background_label.lower()

    def apply_content_surface_styles(self: "NoteCopyPaster", use_background: bool) -> None:
        if not use_background:
            self.table.setStyleSheet("")
            self.table.setShowGrid(True)
            self.grid_sort_bar.setStyleSheet("")
            self.grid_scroll.setStyleSheet("")
            self.grid_container.setStyleSheet("")
            self.title_group.setStyleSheet("")
            self.content_group.setStyleSheet("")
            self.command_group.setStyleSheet("")
            self.title_results.setStyleSheet("")
            self.content_results.setStyleSheet("")
            self.command_results.setStyleSheet("")
            self.command_results_secondary.setStyleSheet("")
            self.search_input.setStyleSheet("")
            self.status_label.setStyleSheet("")
            self.style_grid_sort_controls()
            return

        self.table.setShowGrid(False)
        self.table.setStyleSheet(
            "QTableWidget {"
            "background: transparent;"
            "alternate-background-color: transparent;"
            "border: none;"
            "}"
            "QHeaderView::section {"
            "background-color: rgba(26, 30, 36, 170);"
            "border: 1px solid rgba(255, 255, 255, 35);"
            "padding: 4px 6px;"
            "}"
            "QTableCornerButton::section {"
            "background: transparent;"
            "border: none;"
            "}"
        )
        self.grid_sort_bar.setStyleSheet("#grid-sort-bar { background-color: rgba(20, 24, 28, 110); border-radius: 8px; }")
        self.grid_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.grid_container.setStyleSheet("background: transparent;")
        group_style = (
            "QGroupBox {"
            "background-color: rgba(20, 24, 28, 110);"
            "border: 1px solid rgba(255, 255, 255, 45);"
            "border-radius: 8px;"
            "margin-top: 8px;"
            "padding-top: 8px;"
            "}"
            "QGroupBox::title {"
            "subcontrol-origin: margin;"
            "left: 10px;"
            "padding: 0 6px;"
            "background: rgba(20, 24, 28, 150);"
            "color: rgba(240, 240, 240, 0.95);"
            "}"
        )
        self.title_group.setStyleSheet(group_style)
        self.content_group.setStyleSheet(group_style)
        self.command_group.setStyleSheet(group_style)
        list_style = (
            "QListWidget {"
            "background-color: rgba(255, 255, 255, 20);"
            "border: none;"
            "}"
        )
        self.title_results.setStyleSheet(list_style)
        self.content_results.setStyleSheet(list_style)
        self.command_results.setStyleSheet(list_style)
        self.command_results_secondary.setStyleSheet(list_style)
        self.search_input.setStyleSheet(
            "QLineEdit {"
            "background-color: rgba(255, 255, 255, 205);"
            "color: #111111;"
            "border-radius: 6px;"
            "padding: 3px 6px;"
            "}"
            "QLineEdit::placeholder {"
            "color: rgba(17, 17, 17, 150);"
            "}"
        )
        self.status_label.setStyleSheet(
            "QLabel {"
            "background-color: rgba(20, 24, 28, 125);"
            "color: white;"
            "border-radius: 6px;"
            "padding: 4px 8px;"
            "}"
        )
        self.style_grid_sort_controls()

    def set_background_image(self: "NoteCopyPaster", image_path: Path) -> None:
        self.presentation_controller.set_background_image(image_path)

    def clear_background_image(self: "NoteCopyPaster") -> None:
        self.presentation_controller.clear_background_image()

    def start_background_button_action(self: "NoteCopyPaster") -> None:
        self.presentation_controller.start_background_button_action()

    def clear_background_from_hold(self: "NoteCopyPaster") -> None:
        self.presentation_controller.clear_background_from_hold()

    def finish_background_button_action(self: "NoteCopyPaster") -> None:
        self.presentation_controller.finish_background_button_action()

    def choose_background_image(self: "NoteCopyPaster") -> None:
        self.presentation_controller.choose_background_image()

    def show_toast(self: "NoteCopyPaster", message: str, timeout_ms: int = 2600) -> None:
        self.presentation_controller.show_toast(message, timeout_ms=timeout_ms)

    def show_instruction_banner(self: "NoteCopyPaster", message: str) -> None:
        self.presentation_controller.show_instruction_banner(message)

    def hide_instruction_banner(self: "NoteCopyPaster") -> None:
        self.presentation_controller.hide_instruction_banner()

    def show_terminal_ai_overlay(self: "NoteCopyPaster", message: str) -> None:
        self.presentation_controller.show_terminal_ai_overlay(message)

    def hide_terminal_ai_overlay(self: "NoteCopyPaster") -> None:
        self.presentation_controller.hide_terminal_ai_overlay()

    def position_terminal_ai_overlay(self: "NoteCopyPaster") -> None:
        self.presentation_controller.position_terminal_ai_overlay()

    def schedule_hover_popup(self: "NoteCopyPaster", pending_hover: dict) -> None:
        self.presentation_controller.schedule_hover_popup(pending_hover)

    def cancel_hover_popup(self: "NoteCopyPaster") -> None:
        self.presentation_controller.cancel_hover_popup()

    def show_pending_hover_popup(self: "NoteCopyPaster") -> None:
        self.presentation_controller.show_pending_hover_popup()

    def show_floating_popup(self: "NoteCopyPaster", text: str, global_pos: QPoint, *, width: int, style_sheet: str) -> None:
        self.presentation_controller.show_floating_popup(text, global_pos, width=width, style_sheet=style_sheet)

    def preview_text_for(self: "NoteCopyPaster", target: "SnipcomEntry | Path | str") -> str:
        return self.presentation_controller.preview_text_for(target)

    def show_preview_popup(self: "NoteCopyPaster", target: "SnipcomEntry | Path | str", global_pos: QPoint) -> None:
        self.presentation_controller.show_preview_popup(target, global_pos)

    def show_hint_popup(self: "NoteCopyPaster", text: str, global_pos: QPoint) -> None:
        self.presentation_controller.show_hint_popup(text, global_pos)

    def attach_action_hint(self: "NoteCopyPaster", widget: QWidget, text: str) -> None:
        self.presentation_controller.attach_action_hint(widget, text)

    def scaled_size(self: "NoteCopyPaster", value: int) -> int:
        return max(1, round(value * self.zoom_percent / 100))

    def apply_widget_zoom(self: "NoteCopyPaster", widget: QWidget, base_point_size: int) -> None:
        font = widget.font()
        font.setPointSize(max(7, self.scaled_size(base_point_size)))
        widget.setFont(font)

    def style_grid_sort_controls(self: "NoteCopyPaster") -> None:
        vertical_padding = self.scaled_size(6)
        horizontal_padding = self.scaled_size(14)
        min_height = self.scaled_size(34)
        for button in self.grid_sort_buttons.values():
            button.setStyleSheet(f"padding: {vertical_padding}px {horizontal_padding}px;")
            button.setMinimumHeight(min_height)
            button.adjustSize()

        self.grid_tag_filter_button.setStyleSheet(f"padding: {vertical_padding}px {horizontal_padding}px;")
        self.grid_tag_filter_button.setMinimumHeight(min_height)
        self.grid_tag_filter_button.adjustSize()

    def style_action_button(self: "NoteCopyPaster", widget: QWidget, compact: bool = False) -> None:
        font = widget.font()
        font.setPointSize(max(7, self.scaled_size(10)))
        widget.setFont(font)
        if compact:
            vpad = self.scaled_size(6)
            hpad = self.scaled_size(5)
            radius = self.scaled_size(7)
            widget.setStyleSheet(
                "QPushButton, QToolButton {"
                f"padding: {vpad}px {hpad}px;"
                "background-color: rgba(70, 82, 98, 210);"
                "color: #f4f5f7;"
                "border: 1px solid rgba(255, 255, 255, 48);"
                f"border-radius: {radius}px;"
                "}"
                "QPushButton:hover, QToolButton:hover, QPushButton:focus, QToolButton:focus {"
                "background-color: rgba(88, 102, 120, 224);"
                "border: 1px solid rgba(255, 255, 255, 88);"
                "}"
                "QPushButton:pressed, QToolButton:pressed {"
                "background-color: rgba(58, 70, 84, 232);"
                "}"
            )
            widget.adjustSize()
            width = widget.fontMetrics().horizontalAdvance(widget.text()) + self.scaled_size(24)
            if isinstance(widget, QToolButton):
                width += self.scaled_size(18)
            widget.setFixedWidth(max(width, self.scaled_size(52)))
            return

        vpad = self.scaled_size(6)
        hpad = self.scaled_size(2)
        widget.setStyleSheet(f"padding: {vpad}px {hpad}px;")
        widget.adjustSize()

    def style_grid_overlay_button(
        self: "NoteCopyPaster",
        widget: QWidget,
        *,
        right_divider: bool = False,
        top_divider: bool = False,
    ) -> None:
        font = widget.font()
        font.setPointSize(max(8, self.scaled_size(11)))
        widget.setFont(font)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.setStyleSheet("")
        if isinstance(widget, QToolButton):
            widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            widget.setArrowType(Qt.ArrowType.DownArrow)
            widget.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
