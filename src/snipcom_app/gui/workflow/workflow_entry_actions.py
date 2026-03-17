from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from ...core.helpers import FAVORITES_TAG, available_path, has_tag, join_tags, split_tags
from ...core.repository import SnipcomEntry

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


def rename_file(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return

    prompt_text = entry.name if entry.is_file else entry.display_name
    new_name, accepted = QInputDialog.getText(window, "Rename entry", "New name:", text=prompt_text)
    if not accepted:
        return

    new_name = new_name.strip()
    if not new_name:
        window.show_status("Rename canceled.")
        return

    if "/" in new_name or new_name in {".", ".."}:
        QMessageBox.warning(window, "Invalid name", "Use a plain file name without folders.")
        return

    if entry.is_folder:
        assert entry.path is not None
        new_path = window.repository.texts_dir / new_name
        if new_path == entry.path:
            return
        if new_path.exists():
            QMessageBox.warning(window, "Folder exists", f"{new_path.name} already exists.")
            return
        try:
            renamed_folder = window.repository.rename_folder(entry.path, new_name)
        except OSError as exc:
            QMessageBox.critical(window, "Rename failed", str(exc))
            return
        window.repository.move_metadata(window.tags, window.snip_types, window.launch_options, entry.path, renamed_folder)
        window.repository.reassign_command_folder_prefix(entry.path, renamed_folder)
        window.save_tags()
        window.save_snip_types()
        window.save_launch_options()
        window.push_undo({"type": "rename_folder", "old_path": str(entry.path), "new_path": str(renamed_folder)})
        window.refresh_workflow_views(refresh_search=False)
        window.show_status(f"Renamed {entry.display_name} to {renamed_folder.name}.")
        return

    if entry.backend == "json_command":
        window.repository.user_command_store.update(entry.source_ref, title=new_name)
        window.refresh_table()
        window.show_status(f"Renamed {entry.display_name} to {new_name}.")
        return
    if entry.is_command:
        assert entry.command_id is not None
        if window.repository.command_store.title_exists(new_name, exclude_id=entry.command_id):
            QMessageBox.warning(window, "Command exists", f"{new_name} already exists.")
            return
        window.repository.command_store.update_command(entry.command_id, title=new_name)
        window.push_undo(
            {
                "type": "rename_command",
                "command_id": entry.command_id,
                "old_title": entry.display_name,
                "new_title": new_name,
            }
        )
        window.refresh_table()
        window.show_status(f"Renamed {entry.display_name} to {new_name}.")
        return

    assert entry.path is not None
    fallback_suffix = window.snip_type_fallback_suffix(window.snip_type_for(entry))
    new_path = window.repository.resolve_text_file_path(new_name, fallback_suffix=fallback_suffix)

    if new_path == entry.path:
        return

    if new_path.exists():
        QMessageBox.warning(window, "File exists", f"{new_path.name} already exists.")
        return

    try:
        new_path = window.repository.rename_file(entry.path, new_name, fallback_suffix=fallback_suffix)
    except OSError as exc:
        QMessageBox.critical(window, "Rename failed", str(exc))
        return

    window.move_tag(entry.path, new_path)
    window.push_undo({"type": "rename_file", "old_path": str(entry.path), "new_path": str(new_path)})
    window.refresh_table()
    window.show_status(f"Renamed {entry.display_name} to {new_path.name}.")


def delete_folder_entry(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None or not entry.is_folder or entry.path is None:
        return
    reply = QMessageBox.question(
        window,
        "Move folder to trash",
        f"Move {entry.display_name} to the Trash bin?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply != QMessageBox.StandardButton.Yes:
        return
    try:
        child_entries = window.repository.folder_entries(entry.path, window.tags, window.snip_types)
    except OSError as exc:
        QMessageBox.critical(window, "Move folder to trash failed", str(exc))
        return
    child_entries = [child for child in child_entries if not child.is_folder or child.path != entry.path]
    if child_entries:
        choice_box = QMessageBox(window)
        choice_box.setWindowTitle("Folder contains items")
        choice_box.setText("What do you want to do with the items inside?")
        trash_with_folder_button = choice_box.addButton("Move To Trash Bin With Folder", QMessageBox.ButtonRole.AcceptRole)
        move_to_workflow_button = choice_box.addButton("Move Items To Workflow", QMessageBox.ButtonRole.ActionRole)
        cancel_button = choice_box.addButton(QMessageBox.StandardButton.Cancel)
        choice_box.exec()
        clicked = choice_box.clickedButton()
        if clicked is cancel_button:
            return
        if clicked is move_to_workflow_button:
            try:
                for child in window.repository.folder_visible_children(entry.path):
                    destination = available_path(window.repository.texts_dir, child.name)
                    child.rename(destination)
                    window.repository.move_metadata(window.tags, window.snip_types, window.launch_options, child, destination)
                window.repository.reassign_command_folder_prefix(entry.path, None)
            except OSError as exc:
                QMessageBox.critical(window, "Move items to workflow failed", str(exc))
                return
        elif clicked is trash_with_folder_button:
            folder_key = window.repository.storage_key(entry.path)
            folder_prefix = f"{folder_key}/"
            for record in window.repository.command_store.list_commands(catalog_only=False):
                current_folder = window.repository.command_folder_storage_key(record)
                if current_folder == folder_key or current_folder.startswith(folder_prefix):
                    window.repository.command_store.move_command_to_trash(record.command_id)
    try:
        window.move_paths_to_trash([entry.path])
        window.save_tags()
        window.save_snip_types()
        window.save_launch_options()
    except OSError as exc:
        QMessageBox.critical(window, "Move folder to trash failed", str(exc))
        return
    window.refresh_workflow_views(refresh_search=False)
    window.show_status(f"Moved {entry.display_name} to trash.")


def modify_tag(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None:
        window.refresh_table()
        QMessageBox.warning(window, "Missing entry", "This entry is no longer available.")
        return
    if entry.is_folder:
        QMessageBox.information(window, "Folder action", "Folders do not use tag editing in this view.")
        return

    current_tag = window.tag_for(entry)
    dialog = QInputDialog(window)
    dialog.setWindowTitle("Modify Tag")
    dialog.setLabelText("Tag(s), comma-separated:")
    dialog.setTextValue(current_tag)
    dialog.resize(320, 120)
    dialog.setMinimumWidth(320)
    if dialog.exec() != QInputDialog.DialogCode.Accepted:
        return

    new_tag = join_tags(split_tags(dialog.textValue()))
    if new_tag == current_tag:
        return

    window.set_tag(entry, new_tag)
    effective_new_tag = window.tag_for(entry)
    window.push_undo(
        {
            "type": "modify_tag",
            "entry_id": entry.entry_id,
            "old_tag": current_tag,
            "new_tag": effective_new_tag,
        }
    )
    window.refresh_table()
    if effective_new_tag:
        window.show_status(f"Updated tag for {entry.display_name}.")
    else:
        window.show_status(f"Removed tag from {entry.display_name}.")


def add_entry_to_favorites(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None or entry.is_folder:
        return
    current_tag = window.tag_for(entry)
    if has_tag(split_tags(current_tag), FAVORITES_TAG):
        window.show_status(f"{entry.display_name} is already in favorites.")
        return
    if not window.add_to_favorites(entry):
        return
    new_tag = window.tag_for(entry)
    window.push_undo(
        {
            "type": "modify_tag",
            "entry_id": entry.entry_id,
            "old_tag": current_tag,
            "new_tag": new_tag,
        }
    )
    window.refresh_table()
    window.show_status(f"Added {entry.display_name} to favorites.")


def remove_entry_from_favorites(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None or entry.is_folder:
        return
    current_tag = window.tag_for(entry)
    if not has_tag(split_tags(current_tag), FAVORITES_TAG):
        window.show_status(f"{entry.display_name} is not in favorites.")
        return
    if not window.remove_from_favorites(entry):
        return
    new_tag = window.tag_for(entry)
    window.push_undo(
        {
            "type": "modify_tag",
            "entry_id": entry.entry_id,
            "old_tag": current_tag,
            "new_tag": new_tag,
        }
    )
    window.refresh_table()
    window.show_status(f"Removed {entry.display_name} from favorites.")


def add_description(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None or not entry.is_file:
        return
    current_desc = window.description_for(entry)
    dialog = QInputDialog(window)
    dialog.setWindowTitle("Add / Edit Description")
    dialog.setLabelText("Description for this file:")
    dialog.setTextValue(current_desc)
    dialog.resize(360, 120)
    dialog.setMinimumWidth(320)
    if dialog.exec() != QInputDialog.DialogCode.Accepted:
        return
    new_desc = dialog.textValue().strip()
    if new_desc == current_desc:
        return
    window.set_description(entry, new_desc)
    if new_desc:
        window.show_status(f"Description set for {entry.display_name}.")
    else:
        window.show_status(f"Description cleared for {entry.display_name}.")


def toggle_dangerous(window: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
    entry = window.entry_for(target)
    if entry is None or not entry.is_command or entry.command_id is None:
        return
    window.repository.command_store.update_command(entry.command_id, dangerous=not entry.dangerous)
    window.push_undo(
        {
            "type": "toggle_dangerous",
            "command_id": entry.command_id,
            "old_dangerous": entry.dangerous,
        }
    )
    window.refresh_table()
    if entry.dangerous:
        window.show_status(f"Marked {entry.display_name} as safe.")
    else:
        window.show_status(f"Marked {entry.display_name} as dangerous.")
