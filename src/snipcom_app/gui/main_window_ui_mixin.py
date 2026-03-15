from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QGroupBox,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QStyle,
    QWidget,
)

from ..ai.ai import AISuggestionResult
from .controllers.ai_controller import AiController
from .controllers.presentation_controller import PresentationController
from .controllers.profile_state_controller import FilterController, ProfileController, UiStateController
from ..core.profiles import DEFAULT_PROFILE_SLUG, ProfileManager
from ..core.repository import SnipcomRepository
from .controllers.search_controller import SearchController
from .controllers.settings_controller import SettingsController
from .controllers.terminal_controller import TerminalController
from .controllers.view_controller import ViewController
from .widgets import FlowLayout, GridFileCard, RoundedTableItemDelegate
from .controllers.workflow_controller import WorkflowController
from . import main_window_layout

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowUiMixin:
    def _initialize_runtime_fields(self: "NoteCopyPaster") -> None:
        from . import main_window as main_window_module

        self.startup_aborted = False
        self.setWindowTitle(main_window_module.APP_DISPLAY_NAME)
        self.resize(812, 560)

        self.sort_column = 0
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.undo_stack: list[dict] = []
        self.tags: dict[str, str] = {}
        self.snip_types: dict[str, str] = {}
        self.settings: dict[str, object] = {}
        self.launch_options: dict[str, dict[str, object]] = {}
        self.background_path = ""
        self.action_hints: dict[QWidget, str] = {}
        self.pending_hover: dict | None = None
        self.current_linked_terminal_dir = None
        self.pending_append_output: dict[str, object] | None = None
        self.background_hold_triggered = False
        self.columns_initialized = False
        self.updating_column_layout = False
        self.view_mode = "table"
        self.window_bar_removed = False
        self.dragging_frameless_window = False
        self.frameless_drag_offset = QPoint()
        self.widget_mode = False
        self.widget_mode_bar: QWidget | None = None
        self.top_bar_widget: QWidget | None = None
        self.move_window_handle: QWidget | None = None
        self.store_window: QWidget | None = None
        self.selected_grid_tags: set[str] = set()
        self.selected_family_filter = ""
        self.pinned_families: set[str] = set()
        self.active_folder_popup = None
        self.add_to_folder_target_id = ""
        self.add_to_folder_selected_ids: set[str] = set()
        self.profile_manager = ProfileManager(
            app_support_dir=main_window_module.APP_SUPPORT_DIR,
            app_config_dir=main_window_module.APP_CONFIG_DIR,
            default_settings_path=main_window_module.SETTINGS_FILE,
            default_texts_dir=main_window_module.DEFAULT_TEXTS_DIR,
        )
        self.entries_by_id = {}
        self.grid_cards: dict[str, GridFileCard] = {}
        self.grid_sort_buttons: dict[int, QPushButton] = {}
        self.zoom_percent = 100
        self.table_columns: list[str] = ["name", "family", "tag", "modified", "actions"]
        self.repository = SnipcomRepository(main_window_module.TEXTOS_DIR)

    def _initialize_controllers(self: "NoteCopyPaster") -> None:
        from . import main_window as main_window_module

        self.settings = self.load_settings()
        self.ui_state_controller = UiStateController(self)
        self.quick_search_binding_defaults = main_window_module.QUICK_SEARCH_BINDING_DEFAULTS
        self.quick_search_bindings = self.load_quick_search_bindings()
        self.terminal_suggestion_binding_defaults = main_window_module.TERMINAL_SUGGESTION_BINDING_DEFAULTS
        self.terminal_suggestion_bindings = self.load_terminal_suggestion_bindings()
        self.main_window_binding_defaults = main_window_module.MAIN_WINDOW_BINDING_DEFAULTS
        self.main_window_binding_labels = main_window_module.MAIN_WINDOW_BINDING_LABELS
        self.main_window_bindings = self.load_main_window_bindings()
        self.search_controller = SearchController(self)
        self.workflow_controller = WorkflowController(self)
        self.terminal_controller = TerminalController(
            self, terminal_suggestion_count=main_window_module.TERMINAL_SUGGESTION_COUNT
        )
        self.profile_controller = ProfileController(self, default_profile_slug=DEFAULT_PROFILE_SLUG)
        self.filter_controller = FilterController(self)
        self.ai_controller = AiController(self, terminal_suggestion_count=main_window_module.TERMINAL_SUGGESTION_COUNT)
        self.presentation_controller = PresentationController(
            self,
            texts_dir_getter=lambda: main_window_module.TEXTOS_DIR,
            terminal_suggestion_count=main_window_module.TERMINAL_SUGGESTION_COUNT,
        )
        self.view_controller = ViewController(self)
        self.settings_controller = SettingsController(
            self,
            quick_search_binding_defaults=main_window_module.QUICK_SEARCH_BINDING_DEFAULTS,
            quick_search_binding_labels=main_window_module.QUICK_SEARCH_BINDING_LABELS,
            terminal_suggestion_binding_defaults=main_window_module.TERMINAL_SUGGESTION_BINDING_DEFAULTS,
            terminal_suggestion_binding_labels=main_window_module.TERMINAL_SUGGESTION_BINDING_LABELS,
            move_handle_icon=main_window_module.move_handle_icon,
        )

    def _initialize_ai_runtime_state(self: "NoteCopyPaster", initial_ui_state) -> None:
        self.quick_search_sequence_buffer: list[str] = []
        self.quick_search_pending_action: str | None = None
        self.search_inline_ai_suggestion: AISuggestionResult | None = None
        self.search_inline_ai_error = ""
        self.search_inline_ai_request = ""
        self.search_inline_ai_busy = False
        self.search_inline_ai_last_generated_request = ""
        self.search_inline_ai_last_generated_at = 0.0
        self.terminal_inline_ai_suggestion: AISuggestionResult | None = None
        self.terminal_inline_ai_error = ""
        self.terminal_inline_ai_request = ""
        self.terminal_inline_ai_busy = False
        self.terminal_inline_ai_last_generated_request = ""
        self.terminal_inline_ai_last_generated_at = 0.0
        self.terminal_passive_suggestions: list[str] = []
        self.terminal_passive_signature: tuple[str, str, str] = ("", "", "")
        self.observed_terminal_commands: dict[str, str] = {}
        self.recent_search_queries = list(initial_ui_state.recent_search_queries)

    def _new_search_results_list(self: "NoteCopyPaster") -> QListWidget:
        return main_window_layout.new_search_results_list(self)

    def _new_search_results_group(self: "NoteCopyPaster", title: str, widget: QListWidget) -> QGroupBox:
        return main_window_layout.new_search_results_group(self, title, widget)

    def _build_search_results_widget(self: "NoteCopyPaster") -> None:
        main_window_layout.build_search_results_widget(self)

    def _build_top_bar_controls(self: "NoteCopyPaster", main_window_module) -> None:
        main_window_layout.build_top_bar_controls(self, main_window_module)

    def _build_terminal_toolbar_controls(self: "NoteCopyPaster") -> None:
        main_window_layout.build_terminal_toolbar_controls(self)

    def _build_table_view(self: "NoteCopyPaster") -> None:
        main_window_layout.build_table_view(self)

    def _build_grid_view(self: "NoteCopyPaster") -> None:
        main_window_layout.build_grid_view(self)

    def _build_main_window_shell(self: "NoteCopyPaster", main_window_module) -> None:
        main_window_layout.build_main_window_shell(self, main_window_module)

    def _build_main_window_ui(self: "NoteCopyPaster") -> None:
        main_window_layout.build_main_window_ui(self)

    def _build_window_overlays(self: "NoteCopyPaster") -> None:
        main_window_layout.build_window_overlays(self)

    def _build_window_timers_and_shortcuts(self: "NoteCopyPaster") -> None:
        main_window_layout.build_window_timers_and_shortcuts(self)

    def sync_zoom_slider_to_view(self: "NoteCopyPaster") -> None:
        self.zoom_percent = self.grid_zoom_percent if self.view_mode == "grid" else self.table_zoom_percent
        zoom_min = 30 if self.view_mode == "grid" else 80
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setRange(zoom_min, 140)
        self.zoom_slider.setValue(self.zoom_percent)
        self.zoom_slider.blockSignals(False)

    def apply_zoom(self: "NoteCopyPaster") -> None:
        for widget, base_size in (
            (self.new_button, 11),
            (self.new_folder_button, 11),
            (self.open_folder_button, 11),
            (self.add_selected_to_folder_button, 10),
            (self.cancel_add_to_folder_button, 10),
            (self.undo_button, 11),
            (self.top_more_button, 11),
            (self.search_input, 11),
            (self.main_family_filter_button, 10),
            (self.profile_button, 10),
            (self.status_label, 10),
            (self.grid_tag_filter_button, 10),
        ):
            self.apply_widget_zoom(widget, base_size)

        self.view_toggle_button.setIconSize(QSize(self.scaled_size(18), self.scaled_size(18)))
        self.background_button.setIconSize(QSize(self.scaled_size(18), self.scaled_size(18)))
        self.zoom_slider.setFixedWidth(140)

        for button in self.grid_sort_buttons.values():
            self.apply_widget_zoom(button, 10)
        self.style_grid_sort_controls()

        self.apply_widget_zoom(self.table, 11)
        self.apply_widget_zoom(self.table.horizontalHeader(), 11)
        self.apply_widget_zoom(self.title_results, 12)
        self.apply_widget_zoom(self.content_results, 12)
        self.apply_widget_zoom(self.command_results, 12)
        self.apply_widget_zoom(self.command_results_secondary, 12)
        self.apply_widget_zoom(self.title_group, 12)
        self.apply_widget_zoom(self.content_group, 12)
        self.apply_widget_zoom(self.command_group, 12)
        self.apply_widget_zoom(self.terminal_selector_button, 10)
        self.apply_widget_zoom(self.terminal_command_input, 10)
        self.apply_widget_zoom(self.terminal_ai_suggestion_label, 9)
        overlay_font = self.terminal_ai_overlay.font()
        overlay_font.setPointSize(max(14, self.scaled_size(18)))
        self.terminal_ai_overlay.setFont(overlay_font)
        self.style_terminal_toolbar()
        self.table.verticalHeader().setMinimumSectionSize(self.scaled_size(46))
        self.table.resizeRowsToContents()
        self.view_controller.normalize_row_heights()
        self.update_tag_header_filter_button()

    def handle_zoom_changed(self: "NoteCopyPaster", value: int) -> None:
        self.zoom_percent = value
        if self.view_mode == "grid":
            self.grid_zoom_percent = value
        else:
            self.table_zoom_percent = value
        self.columns_initialized = False
        self.save_runtime_preferences()
        self.apply_zoom()
        self.refresh_table()

    def configure_menu_action(self: "NoteCopyPaster", action: QAction, hint: str) -> QAction:
        action.setToolTip(hint)
        action.setStatusTip(hint)
        action.setWhatsThis(hint)
        return action

    def build_paste_menu(self: "NoteCopyPaster", entry, parent: QWidget) -> QMenu:
        paste_menu = QMenu(parent)

        prepend_action = self.configure_menu_action(
            QAction("Append top", paste_menu),
            "Insert the current clipboard text at the top of this entry.",
        )
        prepend_action.triggered.connect(lambda _checked=False: self.prepend_paste(entry))
        paste_menu.addAction(prepend_action)

        append_action = self.configure_menu_action(
            QAction("Append bottom", paste_menu),
            "Append the current clipboard text to the end of this entry.",
        )
        append_action.triggered.connect(lambda _checked=False: self.append_paste(entry))
        paste_menu.addAction(append_action)

        rewrite_action = self.configure_menu_action(
            QAction("Replace content", paste_menu),
            "Replace this entry content with the current clipboard text.",
        )
        rewrite_action.triggered.connect(lambda _checked=False: self.rewrite_paste(entry))
        paste_menu.addAction(rewrite_action)
        return paste_menu

    def build_more_menu(
        self: "NoteCopyPaster",
        entry,
        parent: QWidget,
        *,
        include_open_action: bool = False,
        include_paste_actions: bool = False,
    ) -> QMenu:
        more_menu = QMenu(parent)

        if entry.is_folder:
            open_action = self.configure_menu_action(
                QAction("Open", more_menu),
                "Open this popup folder.",
            )
            open_action.triggered.connect(lambda _checked=False: self.open_folder_entry(entry))
            more_menu.addAction(open_action)

            add_to_folder_action = self.configure_menu_action(
                QAction("Add items to folder", more_menu),
                "Pick workflow items and move them into this folder.",
            )
            add_to_folder_action.triggered.connect(lambda _checked=False: self.begin_add_to_folder_mode(entry))
            more_menu.addAction(add_to_folder_action)

            explorer_action = self.configure_menu_action(
                QAction("Open In Explorer", more_menu),
                "Open this folder in the system file manager for direct content editing.",
            )
            explorer_action.triggered.connect(lambda _checked=False: self.open_folder_entry(entry, force_edit=True))
            more_menu.addAction(explorer_action)

            more_menu.addSeparator()
            rename_action = self.configure_menu_action(QAction("Rename", more_menu), "Rename this folder.")
            rename_action.triggered.connect(lambda _checked=False: self.rename_file(entry))
            more_menu.addAction(rename_action)
            delete_action = self.configure_menu_action(
                QAction("Delete", more_menu),
                "Delete this folder and all of its contents.",
            )
            delete_action.triggered.connect(lambda _checked=False: self.delete_folder_entry(entry))
            more_menu.addAction(delete_action)
            return more_menu

        if include_open_action:
            open_action = self.configure_menu_action(
                QAction("Open", more_menu),
                "Open this entry in the configured editor or built-in command editor.",
            )
            open_action.triggered.connect(lambda _checked=False: self.open_file(entry))
            more_menu.addAction(open_action)

        if include_paste_actions:
            paste_menu = self.build_paste_menu(entry, more_menu)
            paste_menu.menuAction().setText("Paste")
            paste_menu.menuAction().setToolTip("Open paste actions for this entry.")
            paste_menu.menuAction().setStatusTip("Open paste actions for this entry.")
            more_menu.addMenu(paste_menu)

        if include_open_action or include_paste_actions:
            more_menu.addSeparator()

        rename_action = self.configure_menu_action(QAction("Rename", more_menu), "Rename this entry.")
        rename_action.triggered.connect(lambda _checked=False: self.rename_file(entry))
        more_menu.addAction(rename_action)

        if entry.is_file:
            desc_action = self.configure_menu_action(
                QAction("Add / Edit Description", more_menu),
                "Add or edit a short description for this text file.",
            )
            desc_action.triggered.connect(lambda _checked=False: self.add_description(entry))
            more_menu.addAction(desc_action)

        tag_action = self.configure_menu_action(
            QAction("Modify Tag", more_menu),
            "Edit the tag or tags assigned to this entry.",
        )
        tag_action.triggered.connect(lambda _checked=False: self.modify_tag(entry))
        more_menu.addAction(tag_action)

        if self.is_favorite(entry):
            favorite_action = self.configure_menu_action(
                QAction("Remove from Favorites", more_menu),
                "Remove this entry from the favorites tag.",
            )
            favorite_action.triggered.connect(lambda _checked=False: self.remove_entry_from_favorites(entry))
        else:
            favorite_action = self.configure_menu_action(
                QAction("Add to favorites", more_menu),
                "Add this entry to the favorites tag.",
            )
            favorite_action.triggered.connect(lambda _checked=False: self.add_entry_to_favorites(entry))
        more_menu.addAction(favorite_action)

        snip_type_action = self.configure_menu_action(
            QAction("Change snipType", more_menu),
            "Change whether this entry is a text file or a family command.",
        )
        snip_type_action.triggered.connect(lambda _checked=False: self.change_snip_type(entry))
        more_menu.addAction(snip_type_action)

        if entry.is_command:
            dangerous_label = "Mark Safe" if entry.dangerous else "Mark Dangerous"
            dangerous_action = self.configure_menu_action(
                QAction(dangerous_label, more_menu),
                "Toggle whether this command is highlighted as dangerous or system-changing.",
            )
            dangerous_action.triggered.connect(lambda _checked=False: self.toggle_dangerous(entry))
            more_menu.addAction(dangerous_action)

        launch_options_action = self.configure_menu_action(
            QAction("Launch Options", more_menu),
            "Edit how this entry behaves when launched as a command.",
        )
        launch_options_action.triggered.connect(lambda _checked=False: self.edit_launch_options(entry))
        more_menu.addAction(launch_options_action)

        delete_action = self.configure_menu_action(
            QAction("Delete", more_menu),
            "Move this entry into the custom trash bin.",
        )
        delete_action.triggered.connect(lambda _checked=False: self.trash_file(entry))
        more_menu.addAction(delete_action)
        return more_menu

    def populate_top_more_menu(self: "NoteCopyPaster") -> None:
        self.top_more_menu.clear()

        options_action = QAction("Options", self.top_more_menu)
        options_action.triggered.connect(self.show_options_dialog)
        self.top_more_menu.addAction(options_action)

        self.top_more_menu.addSeparator()

        open_trash_action = QAction("Open Trash Bin", self.top_more_menu)
        open_trash_action.triggered.connect(self.open_trash_bin)
        self.top_more_menu.addAction(open_trash_action)

        restore_action = QAction("Chose Restore Bin Files", self.top_more_menu)
        restore_action.triggered.connect(self.choose_restore_bin_files)
        self.top_more_menu.addAction(restore_action)

        empty_trash_action = QAction("Empty Trash Bin", self.top_more_menu)
        empty_trash_action.triggered.connect(self.empty_trash_bin)
        self.top_more_menu.addAction(empty_trash_action)

        self.top_more_menu.addSeparator()

        reset_action = QAction("Reset defaults", self.top_more_menu)
        reset_action.triggered.connect(self.reset_defaults)
        self.top_more_menu.addAction(reset_action)

        delete_profile_action = QAction("Delete Profile", self.top_more_menu)
        delete_profile_action.triggered.connect(self.delete_current_profile)
        self.top_more_menu.addAction(delete_profile_action)

        search_database_action = QAction("Search Command Database", self.top_more_menu)
        search_database_action.triggered.connect(self.open_store_page)
        self.top_more_menu.addAction(search_database_action)

        self.top_more_menu.addSeparator()

        quit_action = QAction("Quit", self.top_more_menu)
        quit_action.triggered.connect(self.close)
        self.top_more_menu.addAction(quit_action)

    def apply_window_bar_setting(self: "NoteCopyPaster", removed: bool) -> None:
        self.window_bar_removed = removed
        if removed:
            self.settings["remove_window_bar"] = True
        else:
            self.settings.pop("remove_window_bar", None)
        self.save_settings()

        geometry = self.geometry()
        was_maximized = self.isMaximized()
        self.hide()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, removed)
        if was_maximized:
            self.showMaximized()
        else:
            self.show()
            self.setGeometry(geometry)
        self.raise_()
        self.activateWindow()
        self.update_resize_grips()
        self.update_move_window_button()

    def update_resize_grips(self: "NoteCopyPaster") -> None:
        if not hasattr(self, "resize_grips"):
            return

        grip_size = 18
        positions = (
            QPoint(0, 0),
            QPoint(max(0, self.width() - grip_size), 0),
            QPoint(0, max(0, self.height() - grip_size)),
            QPoint(max(0, self.width() - grip_size), max(0, self.height() - grip_size)),
        )
        for grip, position in zip(self.resize_grips, positions):
            grip.move(position)
            grip.raise_()
            grip.setVisible(self.window_bar_removed)

    def minimumSizeHint(self: "NoteCopyPaster") -> QSize:
        if getattr(self, "widget_mode", False):
            return QSize(1, 1)
        return super().minimumSizeHint()

    def toggle_widget_mode(self: "NoteCopyPaster", enabled: bool) -> None:
        self.widget_mode = enabled

        # Sync button checked state without re-firing signal
        if hasattr(self, "widget_mode_button") and self.widget_mode_button.isChecked() != enabled:
            self.widget_mode_button.blockSignals(True)
            self.widget_mode_button.setChecked(enabled)
            self.widget_mode_button.blockSignals(False)

        if self.top_bar_widget is not None:
            self.top_bar_widget.setVisible(not enabled)
        if self.widget_mode_bar is not None:
            self.widget_mode_bar.setVisible(enabled)
        if hasattr(self, "widget_mode_options_button"):
            self.widget_mode_options_button.setVisible(enabled)
        self.table.horizontalHeader().setVisible(not enabled)
        if hasattr(self, "grid_sort_bar"):
            self.grid_sort_bar.setVisible(not enabled)

        # Minimum-size handling: widget mode has no lower bound; normal mode
        # enforces the layout-derived minimum.
        if enabled:
            self.setMinimumSize(1, 1)
        else:
            self.setMinimumSize(0, 0)  # clear override, let layout hint take effect
            natural_min = self.minimumSizeHint()
            if self.width() < natural_min.width() or self.height() < natural_min.height():
                self.resize(
                    max(self.width(), natural_min.width()),
                    max(self.height(), natural_min.height()),
                )

        # Sync frameless window, preserving the pre-widget-mode state for restore
        if enabled:
            self._pre_widget_frameless = self.window_bar_removed
            if not self.window_bar_removed:
                self.apply_window_bar_setting(True)
        else:
            pre = getattr(self, "_pre_widget_frameless", False)
            if self.window_bar_removed != pre:
                self.apply_window_bar_setting(pre)

    def update_move_window_button(self: "NoteCopyPaster") -> None:
        if self.move_window_handle is not None:
            self.move_window_handle.setVisible(self.window_bar_removed and not self.widget_mode)

    def start_move_window_drag(self: "NoteCopyPaster", global_pos: QPoint) -> bool:
        if not self.window_bar_removed:
            return False
        window_handle = self.windowHandle()
        if window_handle is not None and window_handle.startSystemMove():
            return True
        if self.move_window_handle is None:
            return False
        if self.isMaximized():
            return True
        self.dragging_frameless_window = True
        self.frameless_drag_offset = global_pos - self.frameGeometry().topLeft()
        return True

    def finish_move_window_drag(self: "NoteCopyPaster") -> None:
        self.dragging_frameless_window = False

    def move_drag_widget(self: "NoteCopyPaster", source: object) -> bool:
        if source in {self.move_window_handle} or (
            self.move_window_handle is not None and isinstance(source, QWidget) and source.parent() is self.move_window_handle
        ):
            return True
        # In widget mode, dragging anywhere on the widget_mode_bar moves the window
        if self.widget_mode and self.widget_mode_bar is not None and isinstance(source, QWidget):
            if source is self.widget_mode_bar or source.parent() is self.widget_mode_bar:
                return True
        return False

    def show_options_dialog(self: "NoteCopyPaster") -> None:
        self.settings_controller.show_options_dialog()

    def update_view_toggle_button(self: "NoteCopyPaster") -> None:
        from . import main_window as main_window_module

        if self.view_mode == "grid":
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        else:
            icon = main_window_module.grid_dots_icon(18)
        self.view_toggle_button.setIcon(icon)

    def toggle_view_mode(self: "NoteCopyPaster") -> None:
        if self.view_mode == "table":
            self.view_mode = "grid"
            self.view_stack.setCurrentWidget(self.grid_page)
        else:
            self.view_mode = "table"
            self.view_stack.setCurrentWidget(self.table_page)
        self.sync_zoom_slider_to_view()
        self.apply_zoom()
        self.refresh_table()
        self.save_runtime_preferences()
        self.update_view_toggle_button()

    def set_sort_column(self: "NoteCopyPaster", column: int) -> None:
        if self.sort_column == column:
            self.sort_order = (
                Qt.SortOrder.DescendingOrder
                if self.sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self.sort_column = column
            self.sort_order = Qt.SortOrder.AscendingOrder
        self.save_runtime_preferences()
        self.refresh_table()

    def update_grid_sort_buttons(self: "NoteCopyPaster") -> None:
        labels = {0: "Name", 1: "Family", 2: "Tag", 3: "Modified"}
        for column, button in self.grid_sort_buttons.items():
            label = labels[column]
            if self.sort_column == column:
                arrow = "↑" if self.sort_order == Qt.SortOrder.AscendingOrder else "↓"
                button.setText(f"{label} {arrow}")
            else:
                button.setText(label)

    def is_pinned_family(self: "NoteCopyPaster", family_key: str) -> bool:
        return self.filter_controller.is_pinned_family(family_key)

    def pin_family(self: "NoteCopyPaster", family_key: str) -> None:
        self.filter_controller.pin_family(family_key)

    def unpin_family(self: "NoteCopyPaster", family_key: str) -> None:
        self.filter_controller.unpin_family(family_key)

    def toggle_pinned_family(self: "NoteCopyPaster", family_key: str) -> None:
        self.filter_controller.toggle_pinned_family(family_key)

    def rebuild_main_family_filter_menu(self: "NoteCopyPaster") -> None:
        self.filter_controller.rebuild_main_family_filter_menu()

    def update_main_family_filter_button(self: "NoteCopyPaster") -> None:
        self.filter_controller.update_main_family_filter_button()

    def set_selected_family_filter(self: "NoteCopyPaster", family_key: str) -> None:
        self.filter_controller.set_selected_family_filter(family_key)

    def rebuild_profiles_menu(self: "NoteCopyPaster") -> None:
        self.profile_controller.rebuild_profiles_menu()

    def update_profile_button(self: "NoteCopyPaster") -> None:
        self.profile_controller.update_profile_button()

    def create_profile(self: "NoteCopyPaster") -> None:
        self.profile_controller.create_profile()

    def switch_profile(self: "NoteCopyPaster", profile_slug: str, *, force: bool = False) -> None:
        self.profile_controller.switch_profile(profile_slug, force=force)

    def load_profile_state(self: "NoteCopyPaster") -> None:
        self.profile_controller.load_profile_state()

    def delete_current_profile(self: "NoteCopyPaster") -> None:
        self.profile_controller.delete_current_profile()

    def rebuild_grid_tag_filter_menu(self: "NoteCopyPaster") -> None:
        self.filter_controller.rebuild_grid_tag_filter_menu()

    def clear_grid_tag_filters(self: "NoteCopyPaster") -> None:
        self.filter_controller.clear_grid_tag_filters()

    def toggle_grid_tag(self: "NoteCopyPaster", tag: str, checked: bool) -> None:
        self.filter_controller.toggle_grid_tag(tag, checked)

    def show_table_tag_filter_menu(self: "NoteCopyPaster") -> None:
        self.filter_controller.show_table_tag_filter_menu()
