from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QCheckBox, QInputDialog, QMenu, QMessageBox, QWidgetAction

from ...core.app_state import ProfileUiState
from ...core.helpers import FAVORITES_TAG
from ...integration.linked_terminal import close_all_linked_terminal_sessions, linked_terminal_root_dir

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class UiStateController:
    def __init__(self, window: "NoteCopyPaster") -> None:
        self.window = window

    def load_profile_ui_state(self) -> ProfileUiState:
        window = self.window
        settings = window.settings
        legacy_zoom = window.read_int_setting("zoom_percent", 100, 80, 140)
        saved_grid_tags = settings.get("selected_grid_tags", [])
        saved_pinned_families = settings.get("pinned_families", [])
        recent_searches = settings.get("recent_search_queries", [])
        return ProfileUiState(
            remove_window_bar=bool(settings.get("remove_window_bar", False)),
            background_path=str(settings.get("background_path", "")),
            table_zoom_percent=window.read_int_setting("table_zoom_percent", legacy_zoom, 80, 140),
            grid_zoom_percent=window.read_int_setting("grid_zoom_percent", legacy_zoom, 30, 140),
            view_mode=(
                str(settings.get("view_mode", "table"))
                if str(settings.get("view_mode", "table")) in {"table", "grid"}
                else "table"
            ),
            sort_column=window.read_int_setting("sort_column", 0, 0, 3),
            sort_order_desc=str(settings.get("sort_order", "asc")).casefold() == "desc",
            selected_grid_tags={
                str(tag)
                for tag in saved_grid_tags
                if isinstance(saved_grid_tags, list) and str(tag).strip()
            },
            selected_family_filter=str(settings.get("selected_family_filter", "") or "").strip(),
            pinned_families={
                str(family)
                for family in saved_pinned_families
                if isinstance(saved_pinned_families, list) and str(family).strip()
            },
            recent_search_queries=[
                str(value).strip()
                for value in recent_searches
                if isinstance(recent_searches, list) and str(value).strip()
            ][:2],
            window_width=window.read_int_setting("window_width", 812, 640, 4000),
            window_height=window.read_int_setting("window_height", 560, 420, 3000),
        )

    def apply_profile_ui_state(self, state: ProfileUiState) -> None:
        window = self.window
        _valid_keys = {"name", "description", "tag", "family", "modified", "actions"}
        _default_cols = ["name", "family", "tag", "modified", "actions"]
        raw_cols = window.settings.get("table_columns", _default_cols)
        if isinstance(raw_cols, list):
            cleaned = [k for k in raw_cols if k in _valid_keys]
            window.table_columns = cleaned if cleaned else list(_default_cols)
        else:
            window.table_columns = list(_default_cols)
        if state.remove_window_bar != window.window_bar_removed:
            window.apply_window_bar_setting(state.remove_window_bar)
        window.background_path = state.background_path
        window.table_zoom_percent = state.table_zoom_percent
        window.grid_zoom_percent = state.grid_zoom_percent
        window.view_mode = state.view_mode
        window.zoom_percent = window.grid_zoom_percent if window.view_mode == "grid" else window.table_zoom_percent
        window.sort_column = state.sort_column
        window.sort_order = Qt.SortOrder.DescendingOrder if state.sort_order_desc else Qt.SortOrder.AscendingOrder
        window.selected_grid_tags = set(state.selected_grid_tags)
        window.selected_family_filter = state.selected_family_filter
        window.pinned_families = set(state.pinned_families)
        window.recent_search_queries = list(state.recent_search_queries)
        window.resize(state.window_width, state.window_height)

    def save_runtime_preferences(self) -> None:
        window = self.window
        header = window.table.horizontalHeader()
        window.settings.pop("zoom_percent", None)
        window.settings["remove_window_bar"] = window.window_bar_removed
        window.settings["background_path"] = window.background_path
        window.settings["table_zoom_percent"] = window.table_zoom_percent
        window.settings["grid_zoom_percent"] = window.grid_zoom_percent
        window.settings["view_mode"] = window.view_mode
        window.settings["sort_column"] = window.sort_column
        window.settings["sort_order"] = "desc" if window.sort_order == Qt.SortOrder.DescendingOrder else "asc"
        window.settings["selected_grid_tags"] = sorted(window.selected_grid_tags)
        window.settings["selected_family_filter"] = window.selected_family_filter
        window.settings["pinned_families"] = sorted(window.pinned_families)
        window.settings["recent_search_queries"] = list(window.recent_search_queries[:2])
        window.settings["window_width"] = window.width()
        window.settings["window_height"] = window.height()
        window.settings["table_columns"] = list(window.table_columns)
        window.settings["column_widths"] = [window.table.columnWidth(index) for index in range(window.table.columnCount())]
        window.settings["column_order"] = [header.logicalIndex(index) for index in range(header.count())]
        window.save_settings()


class ProfileController:
    def __init__(self, window: "NoteCopyPaster", *, default_profile_slug: str) -> None:
        self.window = window
        self.default_profile_slug = default_profile_slug

    def update_profile_button(self) -> None:
        current_profile = self.window.profile_manager.current_profile()
        self.window.profile_button.setText(f"Profile: {current_profile.display_name}")

    def rebuild_profiles_menu(self) -> None:
        window = self.window
        menu = QMenu(window.profile_button)
        current_profile = window.profile_manager.current_profile()
        for profile in window.profile_manager.list_profiles():
            label = profile.display_name
            action = window.configure_menu_action(
                QAction(label, menu),
                f"Switch to the {profile.display_name} profile.",
            )
            action.setCheckable(True)
            action.setChecked(profile.slug == current_profile.slug)
            action.triggered.connect(lambda _checked=False, slug=profile.slug: self.switch_profile(slug))
            menu.addAction(action)

        menu.addSeparator()
        add_action = window.configure_menu_action(
            QAction("Add New Profile", menu),
            "Create a brand new isolated profile and switch to it.",
        )
        add_action.triggered.connect(self.create_profile)
        menu.addAction(add_action)
        window.profile_menu = menu
        window.profile_button.setMenu(menu)
        self.update_profile_button()

    def create_profile(self) -> None:
        window = self.window
        profile_name, accepted = QInputDialog.getText(window, "Add New Profile", "Profile name:")
        if not accepted:
            return
        profile_name = profile_name.strip()
        if not profile_name:
            window.show_status("Profile creation canceled.")
            return
        try:
            profile = window.profile_manager.create_profile(profile_name)
        except ValueError as exc:
            QMessageBox.warning(window, "Invalid profile", str(exc))
            return
        self.switch_profile(profile.slug, force=True)

    def switch_profile(self, profile_slug: str, *, force: bool = False) -> None:
        window = self.window
        if not force and profile_slug == window.profile_manager.current_profile_slug:
            return
        window.save_runtime_preferences()
        close_all_linked_terminal_sessions(linked_terminal_root_dir())
        window.linked_terminal_timer.stop()
        window.observed_terminal_commands.clear()
        try:
            window.profile_manager.switch_profile(profile_slug)
        except KeyError:
            QMessageBox.warning(window, "Missing profile", "That profile is no longer available.")
            return
        self.load_profile_state()

    def load_profile_state(self) -> None:
        window = self.window
        window.settings = window.load_settings()
        if not window.ensure_texts_root_selected():
            window.profile_manager.switch_profile(self.default_profile_slug)
            window.settings = window.load_settings()
            window.ensure_texts_root_selected()

        window.ensure_storage()
        window.tags = window.load_tags()
        window.snip_types = window.load_snip_types()
        window.launch_options = window.load_launch_options()
        window.observed_terminal_commands.clear()
        profile_ui_state = window.ui_state_controller.load_profile_ui_state()
        window.ui_state_controller.apply_profile_ui_state(profile_ui_state)
        window.undo_stack.clear()
        window.undo_button.setEnabled(False)
        window.pending_append_output = None
        window.current_linked_terminal_dir = None
        window.close_active_folder_popup()
        window.add_to_folder_target_id = ""
        window.add_to_folder_selected_ids.clear()
        window._update_add_to_folder_controls()
        window.columns_initialized = False
        window.search_input.clear()
        window.apply_saved_column_order()
        window.view_stack.setCurrentWidget(window.grid_page if window.view_mode == "grid" else window.table_page)
        window.apply_background()
        window.sync_zoom_slider_to_view()
        window.apply_zoom()
        self.rebuild_profiles_menu()
        window.terminal_controller.refresh_linked_terminal_toolbar()
        window.refresh_workflow_views(refresh_store=window.store_window is not None)
        window.linked_terminal_timer.start(250)
        window.show_status(f"Switched to profile {window.profile_manager.current_profile().display_name}.")

    def delete_current_profile(self) -> None:
        window = self.window
        current_profile = window.profile_manager.current_profile()
        if current_profile.slug == self.default_profile_slug:
            first = QMessageBox.question(
                window,
                "Reset Default Profile",
                "Default profile can not be deleted but can be completely set to default. Do you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if first != QMessageBox.StandardButton.Yes:
                return
            second = QMessageBox.question(
                window,
                "Confirm Reset Default Profile",
                "This will reset the Default profile and clear its workflow, filters, window layout, and saved state. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if second != QMessageBox.StandardButton.Yes:
                return
            close_all_linked_terminal_sessions(linked_terminal_root_dir())
            window.profile_manager.reset_profile(self.default_profile_slug)
            window.profile_manager.switch_profile(self.default_profile_slug)
            self.load_profile_state()
            return

        first = QMessageBox.question(
            window,
            "Delete Profile",
            f"Delete the profile {current_profile.display_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if first != QMessageBox.StandardButton.Yes:
            return
        second = QMessageBox.question(
            window,
            "Confirm Delete Profile",
            f"This will permanently remove the profile {current_profile.display_name} and its saved workflow. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if second != QMessageBox.StandardButton.Yes:
            return

        close_all_linked_terminal_sessions(linked_terminal_root_dir())
        slug = current_profile.slug
        window.profile_manager.delete_profile(slug)
        window.profile_manager.switch_profile(self.default_profile_slug)
        self.load_profile_state()


class FilterController:
    def __init__(self, window: "NoteCopyPaster") -> None:
        self.window = window

    def is_pinned_family(self, family_key: str) -> bool:
        return bool(family_key.strip() and family_key in self.window.pinned_families)

    def _set_family_pinned(self, family_key: str, *, pinned: bool) -> None:
        family_key = family_key.strip()
        if not family_key:
            return
        if pinned:
            if family_key in self.window.pinned_families:
                return
            self.window.pinned_families.add(family_key)
        else:
            if family_key not in self.window.pinned_families:
                return
            self.window.pinned_families.discard(family_key)
        self.window.save_runtime_preferences()
        self.rebuild_main_family_filter_menu()
        self.window.search_controller.update_search_results()

    def pin_family(self, family_key: str) -> None:
        self._set_family_pinned(family_key, pinned=True)

    def unpin_family(self, family_key: str) -> None:
        self._set_family_pinned(family_key, pinned=False)

    def toggle_pinned_family(self, family_key: str) -> None:
        if self.is_pinned_family(family_key):
            self.unpin_family(family_key)
        else:
            self.pin_family(family_key)

    def rebuild_main_family_filter_menu(self) -> None:
        window = self.window
        menu = QMenu(window.main_family_filter_button)
        families = sorted(
            {
                entry.family_key
                for entry in window.active_entries()
                if entry.is_command and entry.family_key.strip()
            }
        )
        all_action = window.configure_menu_action(
            QAction("All Families", menu),
            "Show all workflow entries without family filtering.",
        )
        all_action.setCheckable(True)
        all_action.setChecked(not window.selected_family_filter)
        all_action.triggered.connect(lambda _checked=False: self.set_selected_family_filter(""))
        menu.addAction(all_action)

        if families:
            menu.addSeparator()
        for family in families:
            label = family
            if self.is_pinned_family(family):
                label += " [Pinned]"
            action = window.configure_menu_action(
                QAction(label, menu),
                f"Filter the main workflow to entries related to the {family} family.",
            )
            action.setCheckable(True)
            action.setChecked(window.selected_family_filter == family)
            action.triggered.connect(lambda _checked=False, value=family: self.set_selected_family_filter(value))
            menu.addAction(action)

        window.main_family_filter_menu = menu
        window.main_family_filter_button.setMenu(menu)
        self.update_main_family_filter_button()

    def update_main_family_filter_button(self) -> None:
        if self.window.selected_family_filter:
            self.window.main_family_filter_button.setText(f"Family: {self.window.selected_family_filter}")
        else:
            self.window.main_family_filter_button.setText("Family")

    def set_selected_family_filter(self, family_key: str) -> None:
        window = self.window
        window.selected_family_filter = family_key.strip()
        self.update_main_family_filter_button()
        window.save_runtime_preferences()
        window.refresh_table()

    def rebuild_grid_tag_filter_menu(self) -> None:
        window = self.window
        window.grid_tag_filter_menu.clear()

        clear_action = QAction("All tags", window.grid_tag_filter_menu)
        clear_action.triggered.connect(self.clear_grid_tag_filters)
        window.grid_tag_filter_menu.addAction(clear_action)
        window.grid_tag_filter_menu.addSeparator()

        tags = sorted(
            {FAVORITES_TAG, *(tag for entry in window.active_entries() for tag in window.tags_for(entry))},
            key=str.casefold,
        )
        window.selected_grid_tags.intersection_update(tags)
        for tag in tags:
            checkbox = QCheckBox(tag)
            checkbox.setChecked(tag in window.selected_grid_tags)
            checkbox.stateChanged.connect(
                lambda state, current_tag=tag: self.toggle_grid_tag(
                    current_tag, state == Qt.CheckState.Checked.value
                )
            )
            checkbox_action = QWidgetAction(window.grid_tag_filter_menu)
            checkbox_action.setDefaultWidget(checkbox)
            window.grid_tag_filter_menu.addAction(checkbox_action)

        if window.selected_grid_tags:
            window.grid_tag_filter_button.setText(f"Tag Select ({len(window.selected_grid_tags)})")
        else:
            window.grid_tag_filter_button.setText("Tag Select")

    def clear_grid_tag_filters(self) -> None:
        window = self.window
        if not window.selected_grid_tags:
            return
        window.selected_grid_tags.clear()
        window.save_runtime_preferences()
        window.refresh_table()

    def toggle_grid_tag(self, tag: str, checked: bool) -> None:
        window = self.window
        if checked:
            window.selected_grid_tags.add(tag)
        else:
            window.selected_grid_tags.discard(tag)
        window.save_runtime_preferences()
        window.refresh_table()

    def show_table_tag_filter_menu(self) -> None:
        self.rebuild_grid_tag_filter_menu()
        window = self.window
        window.grid_tag_filter_menu.popup(
            window.tag_filter_header_button.mapToGlobal(window.tag_filter_header_button.rect().bottomLeft())
        )
