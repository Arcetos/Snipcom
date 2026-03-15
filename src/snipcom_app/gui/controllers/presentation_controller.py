from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QPoint, QUrl, Qt
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QWidget

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster
    from ...core.repository import SnipcomEntry


class PresentationController:
    def __init__(self, window: "NoteCopyPaster", *, texts_dir_getter: Callable[[], Path], terminal_suggestion_count: int) -> None:
        self.window = window
        self.texts_dir_getter = texts_dir_getter
        self.terminal_suggestion_count = terminal_suggestion_count

    def set_background_image(self, image_path: Path) -> None:
        window = self.window
        window.background_path = str(image_path)
        window.settings["background_path"] = window.background_path
        window.save_settings()
        self.apply_background()
        window.show_feedback(f"Background image set to {image_path.name}.")

    def clear_background_image(self) -> None:
        window = self.window
        if not window.background_path:
            self.show_toast("Background image is already using the default.")
            return
        window.background_path = ""
        window.settings.pop("background_path", None)
        window.save_settings()
        self.apply_background()
        window.show_feedback("Background image cleared.")

    def apply_background(self) -> None:
        window = self.window
        if not window.background_path:
            window.background_label.clear()
            window.background_label.hide()
            window.apply_content_surface_styles(False)
            return

        background_path = Path(window.background_path)
        if not background_path.exists():
            window.background_path = ""
            window.settings.pop("background_path", None)
            window.save_settings()
            window.background_label.clear()
            window.background_label.hide()
            window.apply_content_surface_styles(False)
            return

        window.background_label.show()
        self.update_background_pixmap()
        window.apply_content_surface_styles(True)

    def update_background_pixmap(self) -> None:
        window = self.window
        if not window.background_path:
            window.background_label.clear()
            window.background_label.hide()
            return

        background_path = Path(window.background_path)
        if not background_path.exists():
            window.background_label.clear()
            window.background_label.hide()
            return

        area = window.centralWidget().rect()
        window.background_label.setGeometry(area)
        if area.width() <= 0 or area.height() <= 0:
            return

        from PyQt6.QtGui import QPixmap

        pixmap = QPixmap(str(background_path))
        if pixmap.isNull():
            window.background_label.clear()
            window.background_label.hide()
            return

        scaled = pixmap.scaled(
            area.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        window.background_label.setPixmap(scaled)
        window.background_label.show()
        window.background_label.lower()

    def start_background_button_action(self) -> None:
        window = self.window
        window.background_hold_triggered = False
        window.background_hold_timer.start(900)

    def clear_background_from_hold(self) -> None:
        self.window.background_hold_triggered = True
        self.clear_background_image()

    def finish_background_button_action(self) -> None:
        window = self.window
        if window.background_hold_timer.isActive():
            window.background_hold_timer.stop()
            self.choose_background_image()
            return
        if window.background_hold_triggered:
            window.background_hold_triggered = False

    def choose_background_image(self) -> None:
        window = self.window
        start_dir = str(Path(window.background_path).parent) if window.background_path else str(self.texts_dir_getter())
        dialog = QFileDialog(window, "Choose background image", start_dir)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilter("Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setSidebarUrls([QUrl.fromLocalFile(str(Path.home())), QUrl.fromLocalFile(str(self.texts_dir_getter()))])
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected_files = dialog.selectedFiles()
        if not selected_files or not selected_files[0]:
            return
        self.set_background_image(Path(selected_files[0]))

    def show_toast(self, message: str, timeout_ms: int = 2600) -> None:
        window = self.window
        window.toast_label.setText(message)
        window.toast_label.adjustSize()
        x = max(12, window.width() - window.toast_label.width() - 16)
        y = max(12, window.height() - window.toast_label.height() - 16)
        window.toast_label.move(x, y)
        window.toast_label.show()
        window.toast_label.raise_()
        window.toast_timer.start(timeout_ms)

    def show_instruction_banner(self, message: str) -> None:
        window = self.window
        window.instruction_banner.setText(message)
        window.instruction_banner.adjustSize()
        x = max(16, (window.width() - window.instruction_banner.width()) // 2)
        y = max(16, (window.height() - window.instruction_banner.height()) // 2)
        window.instruction_banner.move(x, y)
        window.instruction_banner.show()
        window.instruction_banner.raise_()

    def hide_instruction_banner(self) -> None:
        self.window.instruction_banner.hide()

    def show_terminal_ai_overlay(self, message: str) -> None:
        window = self.window
        window.terminal_ai_overlay.setText(message)
        overlay_metrics = window.terminal_ai_overlay.fontMetrics()
        text_lines = message.splitlines() or [""]
        max_line_width = max((overlay_metrics.horizontalAdvance(line) for line in text_lines), default=0)
        horizontal_padding = 32
        vertical_padding = 16
        frame_width = window.terminal_ai_overlay.frameWidth() * 2
        available_width = max(240, window.width() - 32)
        fixed_width = min(available_width, max_line_width + horizontal_padding + frame_width)
        window.terminal_ai_overlay.setFixedWidth(fixed_width)
        fixed_height = overlay_metrics.lineSpacing() * self.terminal_suggestion_count + vertical_padding + frame_width
        window.terminal_ai_overlay.setFixedHeight(fixed_height)
        self.position_terminal_ai_overlay()
        window.terminal_ai_overlay.show()
        window.terminal_ai_overlay.raise_()

    def hide_terminal_ai_overlay(self) -> None:
        self.window.terminal_ai_overlay.hide()

    def position_terminal_ai_overlay(self) -> None:
        window = self.window
        x = max(16, (window.width() - window.terminal_ai_overlay.width()) // 2)
        if window.terminal_toolbar_widget.isVisible():
            toolbar_top_left = window.terminal_toolbar_widget.mapTo(window, QPoint(0, 0))
            y = max(16, toolbar_top_left.y() - window.terminal_ai_overlay.height() - 12)
        else:
            y = max(16, (window.height() - window.terminal_ai_overlay.height()) // 2)
        window.terminal_ai_overlay.move(x, y)

    def schedule_hover_popup(self, pending_hover: dict) -> None:
        window = self.window
        window.pending_hover = pending_hover
        window.hover_popup.hide()
        window.hover_timer.start(1000)

    def cancel_hover_popup(self) -> None:
        window = self.window
        window.pending_hover = None
        window.hover_timer.stop()
        window.hover_popup.hide()

    def show_pending_hover_popup(self) -> None:
        window = self.window
        if not window.pending_hover:
            return
        pending_hover = window.pending_hover
        window.pending_hover = None
        if pending_hover["type"] == "preview":
            self.show_preview_popup(str(pending_hover["entry_id"]), pending_hover["global_pos"])
            return
        if pending_hover["type"] == "hint":
            self.show_hint_popup(pending_hover["text"], pending_hover["global_pos"])

    def show_floating_popup(self, text: str, global_pos: QPoint, *, width: int, style_sheet: str) -> None:
        window = self.window
        window.hover_popup.setStyleSheet(style_sheet)
        window.hover_popup.setMaximumWidth(width)
        window.hover_popup.setText(text)
        window.hover_popup.adjustSize()

        screen = QApplication.primaryScreen()
        available_geometry = screen.availableGeometry() if screen is not None else window.geometry()
        x = global_pos.x() + 18
        y = global_pos.y() + 22

        if x + window.hover_popup.width() > available_geometry.right():
            x = max(available_geometry.left() + 8, global_pos.x() - window.hover_popup.width() - 18)
        if y + window.hover_popup.height() > available_geometry.bottom():
            y = max(available_geometry.top() + 8, global_pos.y() - window.hover_popup.height() - 18)

        window.hover_popup.move(x, y)
        window.hover_popup.show()

    def preview_text_for(self, target: "SnipcomEntry | Path | str") -> str:
        window = self.window
        entry = window.entry_for(target)
        if entry is None:
            return "Preview unavailable: entry is missing."
        content = window.read_entry_text_quiet(entry)
        if content is None:
            return "Preview unavailable."
        lines = content.splitlines()
        preview_lines = lines[:30] or ["(Empty file)"]
        if len(lines) > 30:
            preview_lines.append("...")
        preview_text = "\n".join(preview_lines)
        description = window.description_for(entry)
        if description:
            preview_text += f"\n\n{description}"
        return preview_text

    def show_preview_popup(self, target: "SnipcomEntry | Path | str", global_pos: QPoint) -> None:
        if self.window.entry_for(target) is None:
            return
        self.show_floating_popup(
            self.preview_text_for(target),
            global_pos,
            width=520,
            style_sheet=(
                "QLabel {"
                "background-color: rgba(22, 26, 30, 238);"
                "color: #f0f0f0;"
                "border: 1px solid #4f6672;"
                "border-radius: 10px;"
                "padding: 12px;"
                "font-family: monospace;"
                "}"
            ),
        )

    def show_hint_popup(self, text: str, global_pos: QPoint) -> None:
        self.show_floating_popup(
            text,
            global_pos,
            width=320,
            style_sheet=(
                "QLabel {"
                "background-color: rgba(28, 32, 37, 232);"
                "color: #f7f7f7;"
                "border: 1px solid #5f6b76;"
                "border-radius: 8px;"
                "padding: 9px 11px;"
                "}"
            ),
        )

    def attach_action_hint(self, widget: QWidget, text: str) -> None:
        self.window.action_hints[widget] = text
        widget.installEventFilter(self.window)
