from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMainWindow

from .main_window_dialog_mixin import MainWindowDialogMixin
from .main_window_entry_mixin import MainWindowEntryMixin
from .main_window_history_mixin import MainWindowHistoryMixin
from .main_window_interaction_mixin import MainWindowInteractionMixin
from .main_window_presentation_mixin import MainWindowPresentationMixin
from .main_window_state_mixin import MainWindowStateMixin
from .main_window_table_mixin import MainWindowTableMixin
from .main_window_ui_mixin import MainWindowUiMixin
from .main_window_workflow_mixin import MainWindowWorkflowMixin
from ..integration.linked_terminal import TERMINAL_SUGGESTION_BINDING_DEFAULTS as LINKED_TERMINAL_SUGGESTION_BINDING_DEFAULTS
from ..integration.linked_terminal import TERMINAL_SUGGESTION_COUNT
from ..core.snip_types import SNIP_TYPE_HINTS, SNIP_TYPE_LABELS, SNIP_TYPE_ORDER


APP_DISPLAY_NAME = "Snipcom"
APP_SUPPORT_DIR = Path.home() / ".local" / "share" / "snipcom"
APP_CONFIG_DIR = Path.home() / ".config" / "snipcom"
DEFAULT_TEXTS_DIR = APP_SUPPORT_DIR / "texts"
TEXTOS_DIR = DEFAULT_TEXTS_DIR
APP_STATE_DIRNAME = ".snipcom"
APP_STATE_DIR = TEXTOS_DIR / APP_STATE_DIRNAME
TAGS_FILE = APP_STATE_DIR / "tags.json"
SETTINGS_FILE = APP_CONFIG_DIR / "settings.json"
LAUNCH_OPTIONS_FILE = APP_STATE_DIR / "launch-options.json"
TRASH_DIR = TEXTOS_DIR / "Trash bin"
QUICK_SEARCH_BINDING_DEFAULTS = {
    "focus_results": ["Tab", ""],
    "navigate_up": ["Up", "W"],
    "navigate_down": ["Down", "S"],
    "navigate_left": ["Left", "A"],
    "navigate_right": ["Right", "D"],
    "send_command": ["Return", "Space"],
    "add_to_workspace": ["Ctrl+Return", "Ctrl+Alt+Return"],
    "launch_command": ["Space, E", ""],
    "copy_command": ["Ctrl+C", ""],
}
QUICK_SEARCH_BINDING_LABELS = {
    "focus_results": "Focus results",
    "navigate_up": "Move up",
    "navigate_down": "Move down",
    "navigate_left": "Move left",
    "navigate_right": "Move right",
    "send_command": "Send command",
    "add_to_workspace": "Add to workspace",
    "launch_command": "Launch command",
    "copy_command": "Copy command",
}
TERMINAL_SUGGESTION_BINDING_DEFAULTS = {
    action: list(bindings) for action, bindings in LINKED_TERMINAL_SUGGESTION_BINDING_DEFAULTS.items()
}
TERMINAL_SUGGESTION_BINDING_LABELS = {
    action: f"Insert suggestion {action.rsplit('_', 1)[-1]}" for action in TERMINAL_SUGGESTION_BINDING_DEFAULTS
}
MAIN_WINDOW_BINDING_DEFAULTS = {
    "undo": ["Ctrl+Z", ""],
    "delete_selected": ["Delete", ""],
}
MAIN_WINDOW_BINDING_LABELS = {
    "undo": "Undo",
    "delete_selected": "Move to trash",
}
def app_state_dir_for(texts_dir: Path) -> Path:
    return texts_dir / APP_STATE_DIRNAME


def set_texts_dir(path: Path) -> None:
    global TEXTOS_DIR, APP_STATE_DIR, TAGS_FILE, LAUNCH_OPTIONS_FILE, TRASH_DIR
    TEXTOS_DIR = path
    APP_STATE_DIR = app_state_dir_for(TEXTOS_DIR)
    TAGS_FILE = APP_STATE_DIR / "tags.json"
    LAUNCH_OPTIONS_FILE = APP_STATE_DIR / "launch-options.json"
    TRASH_DIR = TEXTOS_DIR / "Trash bin"


def move_handle_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(Qt.GlobalColor.white)
    pen.setWidth(max(1, size // 12))
    painter.setPen(pen)

    center = size // 2
    margin = max(3, size // 5)
    end = size - margin

    painter.drawLine(center, margin, center, end)
    painter.drawLine(margin, center, end, center)

    head = max(3, size // 5)
    painter.drawLine(center, margin, center - head // 2, margin + head // 2)
    painter.drawLine(center, margin, center + head // 2, margin + head // 2)
    painter.drawLine(center, end, center - head // 2, end - head // 2)
    painter.drawLine(center, end, center + head // 2, end - head // 2)
    painter.drawLine(margin, center, margin + head // 2, center - head // 2)
    painter.drawLine(margin, center, margin + head // 2, center + head // 2)
    painter.drawLine(end, center, end - head // 2, center - head // 2)
    painter.drawLine(end, center, end - head // 2, center + head // 2)
    painter.end()

    return QIcon(pixmap)


def image_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(Qt.GlobalColor.white)
    pen.setWidth(max(1, size // 14))
    painter.setPen(pen)

    margin = max(2, size // 8)
    width = size - margin * 2
    height = size - margin * 2
    painter.drawRoundedRect(margin, margin, width, height, 3, 3)
    painter.drawEllipse(size - margin - size // 4, margin + size // 8, max(2, size // 7), max(2, size // 7))
    painter.drawLine(margin + size // 6, margin + height - size // 5, margin + size // 2, margin + height - size // 2)
    painter.drawLine(margin + size // 2, margin + height - size // 2, size - margin - size // 6, margin + height - size // 3)
    painter.drawLine(margin + size // 3, margin + height - size // 3, margin + size // 2, margin + height - size // 2)
    painter.end()

    return QIcon(pixmap)


def grid_dots_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(Qt.GlobalColor.white)

    dot_size = max(2, size // 6)
    spacing = max(2, size // 7)
    start = (size - (dot_size * 3 + spacing * 2)) // 2
    for row in range(3):
        for column in range(3):
            x = start + column * (dot_size + spacing)
            y = start + row * (dot_size + spacing)
            painter.drawEllipse(x, y, dot_size, dot_size)
    painter.end()

    return QIcon(pixmap)


def search_clear_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(92, 26, 38))
    pen.setWidth(max(2, size // 8))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    margin = max(3, size // 4)
    painter.drawLine(margin, margin, size - margin, size - margin)
    painter.drawLine(size - margin, margin, margin, size - margin)
    painter.end()

    return QIcon(pixmap)


class NoteCopyPaster(
    MainWindowStateMixin,
    MainWindowWorkflowMixin,
    MainWindowHistoryMixin,
    MainWindowInteractionMixin,
    MainWindowUiMixin,
    MainWindowEntryMixin,
    MainWindowPresentationMixin,
    MainWindowTableMixin,
    MainWindowDialogMixin,
    QMainWindow,
):
    def __init__(self) -> None:
        super().__init__()
        self._initialize_runtime_fields()
        self._initialize_controllers()
        initial_ui_state = self.ui_state_controller.load_profile_ui_state()
        self._initialize_ai_runtime_state(initial_ui_state)
        self.window_bar_removed = initial_ui_state.remove_window_bar
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, self.window_bar_removed)
        if not self.ensure_texts_root_selected():
            self.startup_aborted = True
            return

        self.ensure_storage()
        self.tags = self.load_tags()
        self.descriptions = self.repository.load_descriptions()
        self.snip_types = self.load_snip_types()
        self.launch_options = self.load_launch_options()
        self.ui_state_controller.apply_profile_ui_state(initial_ui_state)

        self._build_main_window_ui()
        self._build_window_overlays()
        self._build_window_timers_and_shortcuts()

        self.presentation_controller.apply_background()
        self.filter_controller.rebuild_grid_tag_filter_menu()
        self.profile_controller.rebuild_profiles_menu()
        self.update_grid_sort_buttons()
        self.update_view_toggle_button()
        self.view_stack.setCurrentWidget(self.grid_page if self.view_mode == "grid" else self.table_page)
        self.apply_zoom()
        self.terminal_controller.refresh_linked_terminal_toolbar()
        self.view_controller.refresh_table()
