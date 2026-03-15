from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from ..core.helpers import available_path

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster
    from ..core.repository import SnipcomEntry


class MainWindowHistoryMixin:
    def push_undo(self: "NoteCopyPaster", entry: dict) -> None:
        self.undo_stack.append(entry)
        self.undo_button.setEnabled(True)

    def move_paths_to_trash(self: "NoteCopyPaster", paths: list[Path]) -> list[tuple[Path, Path]]:
        moved_paths = self.repository.move_paths_to_trash(paths, self.tags, self.snip_types, self.launch_options)
        self.save_tags()
        self.save_snip_types()
        self.save_launch_options()
        return moved_paths

    def move_command_entries_to_trash(self: "NoteCopyPaster", entries: list["SnipcomEntry"]) -> list[int]:
        trashed_command_ids: list[int] = []
        for entry in entries:
            if entry.entry_id.startswith("json_command:"):
                uid = entry.entry_id[len("json_command:"):]
                self.repository.user_command_store.delete(uid)
                continue
            if not entry.is_command or entry.command_id is None:
                continue
            self.repository.command_store.move_command_to_trash(entry.command_id)
            trashed_command_ids.append(entry.command_id)
        return trashed_command_ids

    def trash_selected_files(self: "NoteCopyPaster") -> None:
        entries = self.selected_entries()
        if not entries:
            self.show_toast("No entries selected.")
            return

        file_entries = [entry for entry in entries if entry.is_file and entry.path is not None]
        folder_entries = [entry for entry in entries if entry.is_folder]
        command_entries = [entry for entry in entries if entry.is_command]

        # Folders use their own per-folder dialog (delete_folder_entry). If the
        # selection is folders only, skip the batch confirmation and delegate directly.
        if folder_entries and not file_entries and not command_entries:
            for folder_entry in folder_entries:
                self.delete_folder_entry(folder_entry)
            return

        non_folder_count = len(file_entries) + len(command_entries)
        reply = QMessageBox.question(
            self,
            "Move to trash",
            f"Move {non_folder_count} selected item(s) to the Trash bin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            moved_paths = self.move_paths_to_trash([entry.path for entry in file_entries if entry.path is not None])
            trashed_command_ids = self.move_command_entries_to_trash(command_entries)
        except OSError as exc:
            QMessageBox.critical(self, "Move to trash failed", str(exc))
            return

        if not moved_paths and not trashed_command_ids:
            self.refresh_table()
            self.show_toast("Selected entries are no longer available.")
        else:
            undo_entry = {
                "type": "trash_entries",
                "file_moves": [{"original_path": str(original), "trashed_path": str(trashed)} for original, trashed in moved_paths],
                "command_ids": trashed_command_ids,
            }
            self.push_undo(undo_entry)
            self.refresh_table()
            total = len(moved_paths) + len(trashed_command_ids)
            if total == 1:
                name = file_entries[0].display_name if moved_paths else command_entries[0].display_name
                self.show_feedback(f"Moved {name} to trash.")
            else:
                self.show_feedback(f"Moved {total} items to trash.")

        # Handle any folders in a mixed selection after the batch confirmation.
        for folder_entry in folder_entries:
            self.delete_folder_entry(folder_entry)

    def trash_file(self: "NoteCopyPaster", target: "SnipcomEntry | Path | str") -> None:
        entry = self.entry_for(target)
        if entry is None:
            self.refresh_table()
            QMessageBox.warning(self, "Missing entry", "This entry is no longer available.")
            return
        if entry.is_folder:
            QMessageBox.information(self, "Folder action", "Folders are not moved to trash here.")
            return

        reply = QMessageBox.question(
            self,
            "Move to trash",
            f"Move {entry.display_name} to the Trash bin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            moved_paths = self.move_paths_to_trash([entry.path]) if entry.is_file and entry.path is not None else []
            trashed_command_ids = self.move_command_entries_to_trash([entry] if entry.is_command else [])
        except OSError as exc:
            QMessageBox.critical(self, "Move to trash failed", str(exc))
            return

        if not moved_paths and not trashed_command_ids:
            self.refresh_table()
            self.show_toast(f"{entry.display_name} is no longer available.")
            return

        self.push_undo(
            {
                "type": "trash_entries",
                "file_moves": [{"original_path": str(original), "trashed_path": str(trashed)} for original, trashed in moved_paths],
                "command_ids": trashed_command_ids,
            }
        )
        self.refresh_table()
        self.show_status(f"Moved {entry.display_name} to trash.")

    def empty_trash_bin(self: "NoteCopyPaster") -> None:
        files = self.trash_files()
        trashed_commands = self.repository.trashed_command_entries()
        if not files and not trashed_commands:
            self.show_status("Trash bin is already empty.")
            return

        total = len(files) + len(trashed_commands)
        reply = QMessageBox.question(
            self,
            "Empty trash bin",
            f"Permanently remove {total} item(s) from the Trash bin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            file_snapshot = self.repository.empty_trash(files, self.tags, self.snip_types, self.launch_options)
            command_snapshot = self.repository.delete_trashed_commands()
        except OSError as exc:
            QMessageBox.critical(self, "Empty trash failed", str(exc))
            return

        self.save_tags()
        self.save_snip_types()
        self.save_launch_options()

        self.push_undo({"type": "empty_trash", "files": file_snapshot, "commands": command_snapshot})
        self.refresh_table()
        self.show_status(f"Emptied trash bin ({total} item(s) removed).")

    def undo_last_action(self: "NoteCopyPaster") -> None:
        if not self.undo_stack:
            self.undo_button.setEnabled(False)
            self.show_toast("There is no action to undo.")
            return

        entry = self.undo_stack.pop()
        try:
            message = self.apply_undo(entry)
        except OSError as exc:
            QMessageBox.critical(self, "Undo failed", str(exc))
            self.undo_button.setEnabled(bool(self.undo_stack))
            return

        self.undo_button.setEnabled(bool(self.undo_stack))
        self.refresh_table()
        self.show_feedback(message)

    def apply_undo(self: "NoteCopyPaster", entry: dict) -> str:
        action_type = entry["type"]

        if action_type == "create_file":
            path = Path(entry["path"])
            if path.exists():
                path.unlink()
            self.remove_tag(path)
            return f"Undid creation of {path.name}."

        if action_type == "create_folder":
            path = Path(entry["path"])
            if not path.exists():
                return "The created folder is already gone."
            try:
                path.rmdir()
            except OSError:
                return f"Could not undo folder creation because {path.name} is no longer empty."
            return f"Undid creation of {path.name}."

        if action_type == "create_command":
            command_id = int(entry["command_id"])
            try:
                command = self.repository.command_store.get_command(command_id, include_trashed=True)
            except KeyError:
                return "The created command is already gone."
            self.repository.command_store.delete_command(command_id)
            return f"Undid creation of {command.title}."

        if action_type == "create_json_command":
            entry_id = str(entry["id"])
            uid = entry_id[len("json_command:"):]
            try:
                record = self.repository.user_command_store.get(uid)
            except KeyError:
                return "The created command is already gone."
            self.repository.user_command_store.delete(uid)
            return f"Undid creation of {record['title']}."

        if action_type in {"restore_content", "restore_entry_content"}:
            if action_type == "restore_content":
                self.repository.write_text(Path(entry["path"]), entry["previous_content"])
            else:
                self.write_entry_text(entry["entry_id"], entry["previous_content"], "Undo failed")
            return entry["message"]

        if action_type == "rename_file":
            old_path = Path(entry["old_path"])
            new_path = Path(entry["new_path"])
            if new_path.exists():
                restore_path = old_path if not old_path.exists() else available_path(old_path.parent, old_path.name)
                new_path.rename(restore_path)
                self.move_tag(new_path, restore_path)
                return f"Undid rename of {restore_path.name}."
            return f"Could not undo rename because {new_path.name} no longer exists."

        if action_type == "rename_folder":
            old_path = Path(entry["old_path"])
            new_path = Path(entry["new_path"])
            if new_path.exists():
                restore_path = old_path if not old_path.exists() else available_path(old_path.parent, old_path.name)
                new_path.rename(restore_path)
                return f"Undid rename of {restore_path.name}."
            return f"Could not undo folder rename because {new_path.name} no longer exists."

        if action_type == "rename_command":
            command_id = int(entry["command_id"])
            try:
                self.repository.command_store.update_command(command_id, title=str(entry["old_title"]))
            except KeyError:
                return "Could not undo rename because the command no longer exists."
            return f"Undid rename of {entry['old_title']}."

        if action_type == "modify_tag":
            target = entry.get("entry_id") or entry.get("path")
            self.set_tag(str(target) if target is not None else "", entry["old_tag"])
            if entry["old_tag"]:
                return "Restored the previous tag."
            return "Removed the tag that had been added."

        if action_type == "change_snip_type":
            path = Path(entry["path"])
            self.set_snip_type(path, entry["old_snip_type"])
            return entry["message"]

        if action_type == "toggle_dangerous":
            command_id = int(entry["command_id"])
            self.repository.command_store.update_command(command_id, dangerous=bool(entry["old_dangerous"]))
            if entry["old_dangerous"]:
                return "Restored the dangerous flag."
            return "Restored the safe flag."

        if action_type == "change_command_snip_type":
            command_id = int(entry["command_id"])
            self.repository.command_store.update_command(
                command_id,
                snip_type=str(entry["old_snip_type"]),
                family_key=str(entry.get("old_family_key", "")),
                dangerous=bool(entry.get("old_dangerous", False)),
            )
            return "Restored the previous snipType."

        if action_type == "convert_file_to_command":
            command_id = int(entry["command_id"])
            try:
                self.repository.command_store.delete_command(command_id)
            except KeyError:
                pass
            backup_path = Path(entry["backup_path"])
            restore_path = available_path(self.repository.texts_dir, str(entry["original_name"]))
            if backup_path.exists():
                backup_path.rename(restore_path)
            self.set_tag(restore_path, str(entry.get("tag", "")))
            self.set_snip_type(restore_path, "text_file")
            launch_options = entry.get("launch_options") if isinstance(entry.get("launch_options"), dict) else {}
            self.set_launch_options(
                restore_path,
                keep_open=bool(launch_options.get("keep_open", True)),
                ask_extra_arguments=bool(launch_options.get("ask_extra_arguments", False)),
                copy_output_and_close=bool(launch_options.get("copy_output_and_close", False)),
            )
            return f"Restored {restore_path.name} as a text file."

        if action_type == "convert_command_to_file":
            path = Path(entry["path"])
            if path.exists():
                path.unlink()
            self.remove_tag(path)
            restored = self.repository.restore_command_snapshot(entry["command_snapshot"])
            return f"Restored {restored.display_name} as a command."

        if action_type in {"trash_files", "trash_entries"}:
            restored_paths: list[str] = []
            for move in entry.get("moves", entry.get("file_moves", [])):
                original_path = Path(move["original_path"])
                trashed_path = Path(move["trashed_path"])
                if not trashed_path.exists():
                    continue
                restore_path = original_path if not original_path.exists() else available_path(original_path.parent, original_path.name)
                trashed_path.rename(restore_path)
                self.move_tag(trashed_path, restore_path)
                restored_paths.append(restore_path.name)

            restored_commands = 0
            for command_id in entry.get("command_ids", []):
                try:
                    self.repository.command_store.restore_command_from_trash(int(command_id))
                except KeyError:
                    continue
                restored_commands += 1

            total = len(restored_paths) + restored_commands
            if not total:
                return "Could not undo trash because the trashed copies are missing."
            if total == 1:
                return f"Restored {restored_paths[0] if restored_paths else 'command'} from trash."
            return f"Restored {total} items from trash."

        if action_type == "restore_from_trash":
            moved_back: list[str] = []
            for move in entry.get("moves", entry.get("file_moves", [])):
                trashed_path = Path(move["trashed_path"])
                restored_path = Path(move["restored_path"])
                if not restored_path.exists():
                    continue
                move_back_path = trashed_path if not trashed_path.exists() else available_path(trashed_path.parent, trashed_path.name)
                restored_path.rename(move_back_path)
                self.move_tag(restored_path, move_back_path)
                moved_back.append(restored_path.name)

            moved_back_commands = 0
            for command_id in entry.get("command_ids", []):
                try:
                    self.repository.command_store.move_command_to_trash(int(command_id))
                except KeyError:
                    continue
                moved_back_commands += 1

            total = len(moved_back) + moved_back_commands
            if not total:
                return "Could not undo restore because the restored copies are missing."
            if total == 1:
                return f"Moved {moved_back[0] if moved_back else 'command'} back to trash."
            return f"Moved {total} items back to trash."

        if action_type == "empty_trash":
            restored = self.repository.restore_trash_snapshot(entry["files"])
            for file_data in entry["files"]:
                path = available_path(self.repository.trash_dir, file_data["name"])
                self.set_tag(path, file_data["tag"])
                self.set_snip_type(path, file_data.get("snip_type", "text_file"))
            restored_commands = 0
            for snapshot in entry.get("commands", []):
                restored_entry = self.repository.restore_command_snapshot(snapshot)
                if restored_entry.command_id is not None:
                    self.repository.command_store.move_command_to_trash(restored_entry.command_id)
                    restored_commands += 1
            total = restored + restored_commands
            return f"Restored {total} item(s) to the Trash bin."

        return "Undo finished."
