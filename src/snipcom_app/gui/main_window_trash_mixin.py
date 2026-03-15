from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from ..core.helpers import available_path
from ..core.repository import SnipcomEntry

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowTrashMixin:
    # ------------------------------------------------------------------
    # Folder-add mode
    # ------------------------------------------------------------------

    def folder_add_mode_active(self: "NoteCopyPaster") -> bool:
        return bool(self.add_to_folder_target_id)

    def folder_add_target_entry(self: "NoteCopyPaster") -> SnipcomEntry | None:
        return self.entry_for(self.add_to_folder_target_id) if self.add_to_folder_target_id else None

    def is_add_to_folder_candidate(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> bool:
        entry = self.entry_for(target)
        target_entry = self.folder_add_target_entry()
        if entry is None or entry.is_folder or target_entry is None or target_entry.path is None:
            return False
        if entry.is_file and entry.path is not None:
            try:
                entry.path.relative_to(target_entry.path)
                return False
            except ValueError:
                return True
        if entry.entry_id.startswith("json_command:"):
            uid = entry.entry_id[len("json_command:"):]
            try:
                d = self.repository.user_command_store.get(uid)
            except KeyError:
                return False
            return d.get("folder_key", "") != self.repository.storage_key(target_entry.path)
        if entry.is_command and entry.command_id is not None:
            record = self.repository.command_store.get_command(entry.command_id)
            return self.repository.command_folder_storage_key(record) != self.repository.storage_key(target_entry.path)
        return False

    def is_add_to_folder_selected(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> bool:
        entry = self.entry_for(target)
        return entry is not None and entry.entry_id in self.add_to_folder_selected_ids

    def set_add_to_folder_selected(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, selected: bool) -> None:
        entry = self.entry_for(target)
        if entry is None or not self.is_add_to_folder_candidate(entry):
            return
        if selected:
            self.add_to_folder_selected_ids.add(entry.entry_id)
        else:
            self.add_to_folder_selected_ids.discard(entry.entry_id)
        self._update_add_to_folder_controls()
        self.refresh_workflow_views(refresh_search=False)

    def begin_add_to_folder_mode(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        entry = self.entry_for(target)
        if entry is None or not entry.is_folder:
            return
        self.close_active_folder_popup()
        self.add_to_folder_target_id = entry.entry_id
        self.add_to_folder_selected_ids.clear()
        self._update_add_to_folder_controls()
        self.refresh_workflow_views(refresh_search=False)
        self.show_status(f"Select items to add into {entry.display_name}.")

    def cancel_add_to_folder_mode(self: "NoteCopyPaster") -> None:
        self.add_to_folder_target_id = ""
        self.add_to_folder_selected_ids.clear()
        self._update_add_to_folder_controls()
        self.refresh_workflow_views(refresh_search=False)

    def _update_add_to_folder_controls(self: "NoteCopyPaster") -> None:
        active = self.folder_add_mode_active()
        self.add_selected_to_folder_button.setVisible(active)
        self.cancel_add_to_folder_button.setVisible(active)
        self.add_selected_to_folder_button.setEnabled(bool(self.add_to_folder_selected_ids))

    def confirm_add_selected_to_folder(self: "NoteCopyPaster") -> None:
        target_entry = self.folder_add_target_entry()
        if target_entry is None or target_entry.path is None or not self.add_to_folder_selected_ids:
            return
        moved_count = 0
        try:
            for entry_id in sorted(self.add_to_folder_selected_ids):
                entry = self.entry_for(entry_id)
                if entry is None or not self.is_add_to_folder_candidate(entry):
                    continue
                if entry.is_file and entry.path is not None:
                    destination = available_path(target_entry.path, entry.path.name)
                    entry.path.rename(destination)
                    self.repository.move_metadata(self.tags, self.snip_types, self.launch_options, entry.path, destination)
                    moved_count += 1
                elif entry.entry_id.startswith("json_command:"):
                    uid = entry.entry_id[len("json_command:"):]
                    self.repository.set_json_command_folder(uid, target_entry.path)
                    moved_count += 1
                elif entry.is_command and entry.command_id is not None:
                    self.repository.set_command_folder(entry.command_id, target_entry.path)
                    moved_count += 1
            self.save_tags()
            self.save_snip_types()
            self.save_launch_options()
        except OSError as exc:
            QMessageBox.critical(self, "Add to folder failed", str(exc))
            return
        folder_name = target_entry.display_name
        self.add_to_folder_target_id = ""
        self.add_to_folder_selected_ids.clear()
        self._update_add_to_folder_controls()
        self.refresh_workflow_views(refresh_search=False)
        self.show_status(f"Added {moved_count} item(s) to {folder_name}.")

    # ------------------------------------------------------------------
    # Trash bin
    # ------------------------------------------------------------------

    def open_trash_bin(self: "NoteCopyPaster") -> None:
        self._open_workspace_path(self.repository.trash_dir, failure_title="Open trash bin failed")

    def restore_paths_from_trash(self: "NoteCopyPaster", paths: list[Path]) -> list[tuple[Path, Path]]:
        restored_paths = self.repository.restore_paths_from_trash(paths, self.tags, self.snip_types, self.launch_options)
        self.save_tags()
        self.save_snip_types()
        self.save_launch_options()
        return restored_paths

    def restore_commands_from_trash(self: "NoteCopyPaster", command_ids: list[int]) -> list[int]:
        restored_ids: list[int] = []
        for command_id in command_ids:
            try:
                self.repository.command_store.restore_command_from_trash(command_id)
            except KeyError:
                continue
            restored_ids.append(command_id)
        return restored_ids

    def _build_restore_bin_dialog(
        self: "NoteCopyPaster",
        files: list[Path],
        commands: list[SnipcomEntry],
    ) -> tuple[QDialog, QListWidget]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose Restore Bin Files")
        dialog.resize(420, 360)

        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        for path in files:
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "file", "value": str(path)})
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            list_widget.addItem(item)
        for command in commands:
            label = f"[Command] {command.display_name}"
            if command.dangerous:
                label += " [Dangerous]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, {"kind": "command", "value": command.command_id})
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            if command.dangerous:
                item.setForeground(QColor(255, 188, 104))
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        return dialog, list_widget

    def _selected_restore_items(self: "NoteCopyPaster", list_widget: QListWidget) -> tuple[list[Path], list[int]]:
        selected_paths: list[Path] = []
        selected_command_ids: list[int] = []
        for index in range(list_widget.count()):
            item = list_widget.item(index)
            if item.checkState() != Qt.CheckState.Checked:
                continue
            payload = item.data(Qt.ItemDataRole.UserRole)
            if payload["kind"] == "file":
                selected_paths.append(Path(payload["value"]))
            else:
                selected_command_ids.append(int(payload["value"]))
        return selected_paths, selected_command_ids

    def _notify_restore_result(
        self: "NoteCopyPaster",
        restored_paths: list[tuple[Path, Path]],
        restored_command_ids: list[int],
    ) -> None:
        total = len(restored_paths) + len(restored_command_ids)
        if total == 1:
            if restored_paths:
                name = restored_paths[0][1].name
            else:
                command_entry = self.repository.entry_from_id(f"command:{restored_command_ids[0]}", self.tags, self.snip_types)
                name = command_entry.display_name if command_entry is not None else "command"
            self.show_feedback(f"Restored {name} from trash.")
            return
        self.show_feedback(f"Restored {total} items from trash.")

    def choose_restore_bin_files(self: "NoteCopyPaster") -> None:
        files = sorted(self.trash_files(), key=lambda path: path.name.casefold())
        commands = sorted(self.repository.trashed_command_entries(), key=lambda entry: entry.display_name.casefold())
        if not files and not commands:
            self.show_toast("Trash bin is empty.")
            return

        dialog, list_widget = self._build_restore_bin_dialog(files, commands)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_paths, selected_command_ids = self._selected_restore_items(list_widget)

        if not selected_paths and not selected_command_ids:
            self.show_toast("No trash-bin items selected.")
            return

        try:
            restored_paths = self.restore_paths_from_trash(selected_paths)
            restored_command_ids = self.restore_commands_from_trash(selected_command_ids)
        except OSError as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))
            return

        if not restored_paths and not restored_command_ids:
            self.refresh_table()
            self.show_toast("Selected trash-bin items are no longer available.")
            return

        undo_moves = [{"trashed_path": str(trashed), "restored_path": str(restored)} for trashed, restored in restored_paths]
        self.push_undo({"type": "restore_from_trash", "file_moves": undo_moves, "command_ids": restored_command_ids})
        self.refresh_table()
        self._notify_restore_result(restored_paths, restored_command_ids)
