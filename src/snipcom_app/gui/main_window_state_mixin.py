from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from ..ai.ai_shared import ai_enabled, ai_endpoint, ai_model, ai_provider, ai_timeout_seconds
from ..core.helpers import natural_request_text, normalize_binding_sequences
_LEGACY_DEFAULT_TEXTS_DIR = Path.home() / ".local" / "share" / "Texts"

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster
    from ..core.repository import SnipcomEntry
class MainWindowStateMixin:
    def ensure_storage(self: "NoteCopyPaster") -> None:
        self.profile_manager.app_support_dir.mkdir(parents=True, exist_ok=True)
        self.profile_manager.app_config_dir.mkdir(parents=True, exist_ok=True)
        self.repository.ensure_storage()

    def migrate_legacy_default_texts_root(self: "NoteCopyPaster", legacy_path: Path) -> Path:
        target = self.profile_manager.default_texts_dir_path
        target.mkdir(parents=True, exist_ok=True)
        if not legacy_path.is_dir() or legacy_path.resolve() == target.resolve():
            return target

        ignored_files = {self.profile_manager.app_support_dir / "settings.json"}
        for child in legacy_path.iterdir():
            if child in ignored_files:
                continue
            destination = target / child.name
            if destination.exists():
                continue
            try:
                shutil.move(str(child), str(destination))
            except OSError:
                continue
        return target

    def ensure_texts_root_selected(self: "NoteCopyPaster") -> bool:
        saved_path = str(self.settings.get("texts_dir", "")).strip()
        if saved_path:
            candidate = Path(saved_path).expanduser()
            if candidate in {
                _LEGACY_DEFAULT_TEXTS_DIR,
                self.profile_manager.app_support_dir,
            }:
                migrated = self.migrate_legacy_default_texts_root(candidate)
                self.set_texts_root(migrated)
                return True
            if candidate.is_dir():
                self.set_texts_root(candidate)
                return True

        current_profile = self.profile_manager.current_profile()
        if not current_profile.is_default:
            profile_texts_dir = self.profile_manager.default_texts_dir()
            profile_texts_dir.mkdir(parents=True, exist_ok=True)
            self.set_texts_root(profile_texts_dir)
            return True

        message_box = QMessageBox(self)
        message_box.setWindowTitle(self.windowTitle())
        message_box.setText("Choose the folder that will contain this app's text files.")
        message_box.setInformativeText(
            "You can browse to an existing folder or auto-create ~/.local/share/snipcom/texts."
        )
        browse_button = message_box.addButton("Browse", QMessageBox.ButtonRole.AcceptRole)
        auto_create_button = message_box.addButton("Auto Create", QMessageBox.ButtonRole.ActionRole)
        cancel_button = message_box.addButton(QMessageBox.StandardButton.Cancel)
        message_box.exec()

        clicked = message_box.clickedButton()
        if clicked == cancel_button:
            return False

        if clicked == auto_create_button:
            path = self.profile_manager.default_texts_dir_path
            path.mkdir(parents=True, exist_ok=True)
            self.set_texts_root(path)
            return True

        if clicked == browse_button:
            selected = QFileDialog.getExistingDirectory(self, "Choose text folder", str(Path.home()))
            if not selected:
                return False
            self.set_texts_root(Path(selected))
            return True

        return False

    def set_texts_root(self: "NoteCopyPaster", path: Path) -> None:
        from . import main_window as main_window_module

        main_window_module.set_texts_dir(path)
        self.repository.set_texts_dir(path)
        self.settings["texts_dir"] = str(path)
        self.save_settings()

    def load_tags(self: "NoteCopyPaster") -> dict[str, str]:
        return self.repository.load_tags()

    def load_snip_types(self: "NoteCopyPaster") -> dict[str, str]:
        return self.repository.load_snip_types()

    def load_settings(self: "NoteCopyPaster") -> dict[str, object]:
        settings_path = self.profile_manager.settings_path()
        if not settings_path.exists():
            legacy_settings_file = self.profile_manager.app_support_dir / "settings.json"
            if settings_path != self.profile_manager.default_settings_path:
                return {}
            if not legacy_settings_file.exists():
                return {}
            try:
                data = json.loads(legacy_settings_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
            if not isinstance(data, dict):
                return {}
            normalized = {str(key): value for key, value in data.items() if value is not None}
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
            try:
                legacy_settings_file.unlink()
            except OSError:
                pass
            return normalized

        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        return {str(key): value for key, value in data.items() if value is not None}

    def save_settings(self: "NoteCopyPaster") -> None:
        settings_path = self.profile_manager.settings_path()
        if not self.settings:
            try:
                settings_path.unlink()
            except FileNotFoundError:
                pass
            return

        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(self.settings, indent=2, sort_keys=True), encoding="utf-8")

    def load_quick_search_bindings(self: "NoteCopyPaster") -> dict[str, list[str]]:
        return normalize_binding_sequences(
            self.settings.get("quick_search_bindings", {}),
            self.quick_search_binding_defaults,
            slot_count=2,
        )

    def save_quick_search_bindings(self: "NoteCopyPaster") -> None:
        self.settings["quick_search_bindings"] = {
            action: list(values) for action, values in self.quick_search_bindings.items()
        }
        self.save_settings()

    def load_terminal_suggestion_bindings(self: "NoteCopyPaster") -> dict[str, list[str]]:
        return normalize_binding_sequences(
            self.settings.get("terminal_suggestion_bindings", {}),
            self.terminal_suggestion_binding_defaults,
            slot_count=2,
        )

    def save_terminal_suggestion_bindings(self: "NoteCopyPaster") -> None:
        self.settings["terminal_suggestion_bindings"] = {
            action: list(values) for action, values in self.terminal_suggestion_bindings.items()
        }
        self.save_settings()

    def load_main_window_bindings(self: "NoteCopyPaster") -> dict[str, list[str]]:
        return normalize_binding_sequences(
            self.settings.get("main_window_bindings", {}),
            self.main_window_binding_defaults,
            slot_count=2,
        )

    def save_main_window_bindings(self: "NoteCopyPaster") -> None:
        self.settings["main_window_bindings"] = {
            action: list(values) for action, values in self.main_window_bindings.items()
        }
        self.save_settings()

    def add_command_to_workflow(self: "NoteCopyPaster", entry: "SnipcomEntry") -> bool:
        if not entry.is_command or entry.command_id is None:
            return False
        try:
            cloned_entry = self.repository.clone_command_to_workflow(entry.command_id, entry.snip_type)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Add to workspace failed", str(exc))
            return True
        self.push_undo({"type": "create_command", "command_id": cloned_entry.command_id})
        self.refresh_workflow_views(refresh_store=True)
        self.show_status(f"Added {entry.display_name} to the active workflow.")
        self.show_toast(f"Added {entry.display_name} to the workspace.")
        return True

    def save_tags(self: "NoteCopyPaster") -> None:
        self.repository.save_tags(self.tags)

    def save_snip_types(self: "NoteCopyPaster") -> None:
        self.repository.save_snip_types(self.snip_types)

    def load_launch_options(self: "NoteCopyPaster") -> dict[str, dict[str, object]]:
        return self.repository.load_launch_options()

    def save_launch_options(self: "NoteCopyPaster") -> None:
        self.repository.save_launch_options(self.launch_options)

    def read_int_setting(
        self: "NoteCopyPaster",
        key: str,
        default: int,
        minimum: int | None = None,
        maximum: int | None = None,
    ) -> int:
        value = self.settings.get(key, default)
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        if minimum is not None:
            number = max(minimum, number)
        if maximum is not None:
            number = min(maximum, number)
        return number

    def save_runtime_preferences(self: "NoteCopyPaster") -> None:
        self.ui_state_controller.save_runtime_preferences()

    def current_terminal_label(self: "NoteCopyPaster") -> str:
        value = str(self.settings.get("terminal_executable", "")).strip()
        return value or "Automatic detection"

    def current_folder_opener_label(self: "NoteCopyPaster") -> str:
        value = str(self.settings.get("folder_opener_executable", "")).strip()
        return value or "Automatic detection"

    def ai_enabled(self: "NoteCopyPaster") -> bool:
        return ai_enabled(self.settings)

    def ai_provider(self: "NoteCopyPaster") -> str:
        return ai_provider(self.settings)

    def ai_endpoint(self: "NoteCopyPaster") -> str:
        return ai_endpoint(self.settings)

    def ai_model(self: "NoteCopyPaster") -> str:
        return ai_model(self.settings)

    def ai_timeout_seconds(self: "NoteCopyPaster") -> int:
        return ai_timeout_seconds(self.settings)

    def natural_request_text(self: "NoteCopyPaster", text: str) -> str:
        return natural_request_text(text)

    def reset_saved_override(self: "NoteCopyPaster", setting_key: str) -> None:
        if setting_key in self.settings:
            self.settings.pop(setting_key, None)
            self.save_settings()

    def apply_texts_root_change(self: "NoteCopyPaster", path: Path) -> None:
        self.set_texts_root(path)
        self.ensure_storage()
        self.tags = self.load_tags()
        self.descriptions = self.repository.load_descriptions()
        self.snip_types = self.load_snip_types()
        self.launch_options = self.load_launch_options()
        self.selected_grid_tags.clear()
        self.search_input.clear()
        self.filter_controller.rebuild_grid_tag_filter_menu()
        self.view_controller.refresh_table()
        self.show_feedback(f"Text folder set to {path}.")

    def change_texts_folder(self: "NoteCopyPaster", parent: QWidget | None = None) -> bool:
        selected = QFileDialog.getExistingDirectory(parent or self, "Choose text folder", str(self.repository.texts_dir))
        if not selected:
            return False
        self.apply_texts_root_change(Path(selected))
        return True
