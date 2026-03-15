from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from ...core.helpers import available_path, join_tags

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster
    from ...core.repository import SnipcomEntry


class WorkflowController:
    def __init__(self, window: "NoteCopyPaster") -> None:
        self.window = window

    def create_new_file(self) -> None:
        window = self.window
        snip_type = window.prompt_snip_type("text_file")
        if snip_type is None:
            return

        if snip_type == "family_command":
            result = window.prompt_new_user_command()
            if result is None:
                return
            title, body, description = result
            title = title.strip()
            if not title:
                window.show_status("Command creation canceled.")
                return
            try:
                entry = window.repository.create_user_command(title, body, description)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(window, "Create failed", str(exc))
                return
            window.push_undo({"type": "create_json_command", "id": entry.entry_id})
            window.refresh_table()
            window.show_status(f"Created {entry.display_name}.")
            return

        default_name = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_name, open_after_create, initial_content = window.prompt_new_file(default_name)
        if file_name is None:
            return

        file_name = file_name.strip()
        if not file_name:
            window.show_status("File creation canceled.")
            return

        if "/" in file_name or file_name in {".", ".."}:
            QMessageBox.warning(window, "Invalid name", "Use a plain file name without folders.")
            return

        path = window.repository.resolve_text_file_path(
            file_name, fallback_suffix=window.snip_type_fallback_suffix(snip_type)
        )

        if path.exists():
            QMessageBox.warning(window, "File exists", f"{path.name} already exists.")
            return

        try:
            path = window.repository.create_file(
                file_name, fallback_suffix=window.snip_type_fallback_suffix(snip_type)
            )
        except OSError as exc:
            QMessageBox.critical(window, "Create failed", str(exc))
            return

        if initial_content.strip():
            try:
                path.write_text(initial_content, encoding="utf-8")
            except OSError:
                pass

        window.set_snip_type(path, snip_type)
        window.push_undo({"type": "create_file", "path": str(path)})
        window.refresh_table()
        window.show_status(f"Created {path.name}.")
        if open_after_create:
            window.open_file(path)

    def create_new_folder(self) -> None:
        window = self.window
        default_name = f"folder_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        folder_name, folder_mode = window.prompt_new_folder(default_name)
        if folder_name is None:
            return

        folder_name = folder_name.strip()
        if not folder_name:
            window.show_status("Folder creation canceled.")
            return
        if "/" in folder_name or folder_name in {".", ".."}:
            QMessageBox.warning(window, "Invalid name", "Use a plain folder name without nested paths.")
            return

        path = window.repository.texts_dir / folder_name
        if path.exists():
            QMessageBox.warning(window, "Folder exists", f"{path.name} already exists.")
            return
        try:
            created = window.repository.create_folder(folder_name, mode=folder_mode)
        except OSError as exc:
            QMessageBox.critical(window, "Create failed", str(exc))
            return

        window.push_undo({"type": "create_folder", "path": str(created)})
        window.refresh_table()
        window.show_status(f"Created {created.name} (pop up folder).")

    def change_snip_type(self, target: "SnipcomEntry | Path | str") -> None:
        window = self.window
        entry = window.entry_for(target)
        if entry is None:
            window.refresh_table()
            QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
            return

        current_snip_type = window.snip_type_for(entry)
        new_snip_type = window.prompt_snip_type(current_snip_type)
        if new_snip_type is None or new_snip_type == current_snip_type:
            return

        if entry.is_file:
            assert entry.path is not None
            current_content = window.read_file_text(entry, "snipType change failed")
            if current_content is None:
                return
            current_tag = window.tag_for(entry)
            current_launch_options = window.launch_options_for(entry)
            command_attributes = window.prompt_command_attributes(new_snip_type)
            if command_attributes is None:
                return
            family_key, dangerous = command_attributes
            record = window.repository.command_store.create_command(
                window.repository.unique_command_title(entry.display_name),
                body=current_content,
                snip_type=new_snip_type,
                family_key=family_key,
                dangerous=dangerous,
                source_kind="converted-file",
                source_ref=window.repository.storage_key(entry.path),
                launch_options=current_launch_options,
                tags=window.tags_for(entry),
            )
            backup_path = window.repository.move_file_to_command_backup(entry.path)
            window.remove_tag(entry.path)
            window.push_undo(
                {
                    "type": "convert_file_to_command",
                    "command_id": record.command_id,
                    "backup_path": str(backup_path),
                    "original_name": entry.path.name,
                    "tag": current_tag,
                    "launch_options": current_launch_options,
                }
            )
            window.refresh_table()
            window.show_feedback(f"Converted {entry.display_name} into {window.snip_type_label_for(record.snip_type)}.")
            return

        assert entry.command_id is not None
        record = window.repository.command_store.get_command(entry.command_id)
        if new_snip_type == "text_file":
            path = available_path(window.repository.texts_dir, f"{entry.display_name}.txt")
            try:
                window.repository.write_text(path, record.body)
            except OSError as exc:
                QMessageBox.critical(window, "snipType change failed", str(exc))
                return
            window.set_tag(path, join_tags(record.tags))
            window.set_snip_type(path, "text_file")
            window.set_launch_options(
                path,
                keep_open=bool(record.launch_options.get("keep_open", True)),
                ask_extra_arguments=bool(record.launch_options.get("ask_extra_arguments", False)),
                copy_output_and_close=bool(record.launch_options.get("copy_output_and_close", False)),
            )
            snapshot = window.repository.command_snapshot(entry.command_id)
            window.repository.command_store.delete_command(entry.command_id)
            window.push_undo(
                {
                    "type": "convert_command_to_file",
                    "path": str(path),
                    "command_snapshot": snapshot,
                }
            )
            window.refresh_table()
            window.show_feedback(f"Converted {entry.display_name} into Text file.")
            return

        family_key = record.family_key
        dangerous = record.dangerous
        attributes = window.prompt_command_attributes(
            new_snip_type,
            current_family_key=family_key,
            dangerous=dangerous,
            window_title="Change snipType",
        )
        if attributes is None:
            return
        family_key, dangerous = attributes

        window.repository.command_store.update_command(
            entry.command_id,
            snip_type=new_snip_type,
            family_key=family_key if new_snip_type == "family_command" else "",
            dangerous=dangerous,
        )
        window.push_undo(
            {
                "type": "change_command_snip_type",
                "command_id": entry.command_id,
                "old_snip_type": current_snip_type,
                "old_family_key": record.family_key,
                "old_dangerous": record.dangerous,
            }
        )
        window.refresh_table()
        window.show_status(f"Changed snipType for {entry.display_name} to {window.snip_type_label_for(new_snip_type)}.")
        window.show_toast(f"Changed snipType for {entry.display_name}.")
