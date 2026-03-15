from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PyQt6.QtWidgets import (
    QInputDialog,
    QMenu,
    QMessageBox,
)

from ...core.repository import SnipcomEntry

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class StoreActionsMixin:
    """Mixin providing entry-level and family-level action methods for StoreWindow."""

    manager: "NoteCopyPaster"

    # These are provided by StoreWindow (declared here for type-checking only)
    def selected_entry(self) -> SnipcomEntry | None: ...  # type: ignore[empty-body]
    def catalog_entries(self) -> list[SnipcomEntry]: ...  # type: ignore[empty-body]
    def refresh_entries(self) -> None: ...  # type: ignore[empty-body]

    def open_selected_entry(self, *_args: object) -> None:
        self._apply_selected_entry_action(self.manager.open_file)

    def copy_selected_entry(self) -> None:
        self._apply_selected_entry_action(self.manager.copy_content)

    def send_selected_entry(self) -> None:
        self._apply_selected_entry_action(self.manager.send_file_content)

    def launch_selected_entry(self) -> None:
        self._apply_selected_entry_action(self.manager.launch_file_content)

    def _apply_selected_entry_action(self, action: Callable[[SnipcomEntry], None]) -> None:
        entry = self.selected_entry()
        if entry is None:
            return
        action(entry)

    def add_selected_to_workflow(self, target_snip_type: str) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.is_command or entry.command_id is None:
            return
        try:
            cloned_entry = self.manager.repository.clone_command_to_workflow(entry.command_id, target_snip_type)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Add to workflow failed", str(exc))  # type: ignore[arg-type]
            return

        if cloned_entry.is_file and cloned_entry.path is not None:
            self.manager.set_snip_type(cloned_entry, "text_file")
            self.manager.set_tag(cloned_entry, entry.tag_text)
            options = self.manager.launch_options_for(entry)
            self.manager.set_launch_options(
                cloned_entry,
                keep_open=bool(options["keep_open"]),
                ask_extra_arguments=bool(options["ask_extra_arguments"]),
                copy_output_and_close=bool(options["copy_output_and_close"]),
            )
            self.manager.push_undo({"type": "create_file", "path": str(cloned_entry.path)})
        else:
            self.manager.push_undo({"type": "create_command", "command_id": cloned_entry.command_id})
        self.manager.refresh_workflow_views(refresh_store=True)
        self.manager.show_status(f"Added {entry.display_name} to the active workflow.")

    def toggle_selected_family_pin(self) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.family_key:
            return
        was_pinned = self.manager.is_pinned_family(entry.family_key)
        self.manager.toggle_pinned_family(entry.family_key)
        if was_pinned:
            self.manager.show_status(f"Unpinned family {entry.family_key}.")
        else:
            self.manager.show_status(f"Pinned family {entry.family_key}.")
        self.refresh_entries()

    def delete_selected_entry(self) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.is_command or entry.command_id is None:
            return
        reply = QMessageBox.question(
            self,  # type: ignore[arg-type]
            "Delete command",
            f"Delete '{entry.display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.manager.repository.command_store.delete_command(entry.command_id)
        self.manager.update_search_results()
        self.refresh_entries()
        self.manager.show_status(f"Deleted '{entry.display_name}'.")

    def tag_selected_entry(self) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.is_command or entry.command_id is None:
            return
        try:
            record = self.manager.repository.command_store.get_command(entry.command_id)
        except KeyError:
            return
        current_tags = ", ".join(record.tags) if record.tags else "(none)"
        tag, ok = QInputDialog.getText(
            self,  # type: ignore[arg-type]
            "Add to Tag",
            f"Tag to add to '{entry.display_name}':\nCurrent tags: {current_tags}",
        )
        if not ok or not tag.strip():
            return
        new_tag = tag.strip()
        existing = list(record.tags)
        if not any(t.casefold() == new_tag.casefold() for t in existing):
            existing.append(new_tag)
        self.manager.repository.command_store.update_command(entry.command_id, tags=existing)
        self.refresh_entries()
        self.manager.show_status(f"Added tag '{new_tag}' to '{entry.display_name}'.")

    def _show_entry_context_menu(self, pos: object) -> None:
        from PyQt6.QtWidgets import QListWidget
        entry_list: QListWidget = self.entry_list  # type: ignore[attr-defined]
        if entry_list.itemAt(pos) is None:  # type: ignore[arg-type]
            return
        entry = self.selected_entry()
        menu = QMenu(self)  # type: ignore[arg-type]
        if entry is not None:
            menu.addAction("Copy", self.copy_selected_entry)
            menu.addAction("Send Command", self.send_selected_entry)
            menu.addAction("Launch", self.launch_selected_entry)
            menu.addSeparator()
            menu.addAction("Add as Text to Workflow", lambda: self.add_selected_to_workflow("text_file"))
            menu.addAction("Add as Family to Workflow", lambda: self.add_selected_to_workflow("family_command"))
            menu.addSeparator()
            menu.addAction("Add to Tag...", self.tag_selected_entry)
            if entry.is_command:
                menu.addSeparator()
                menu.addAction("Delete...", self.delete_selected_entry)
        menu.exec(entry_list.mapToGlobal(pos))  # type: ignore[arg-type]

    def _show_family_context_menu(self, pos: object) -> None:
        from PyQt6.QtWidgets import QListWidget
        family_list: QListWidget = self.family_list  # type: ignore[attr-defined]
        item = family_list.itemAt(pos)  # type: ignore[arg-type]
        if item is None:
            return
        family_key = str(item.data(0x0100) or "")
        if not family_key:
            return  # "All Families" row — no actions
        menu = QMenu(self)  # type: ignore[arg-type]
        menu.addAction(f"Delete family '{family_key}'...", self._delete_family_by_key(family_key))
        menu.exec(family_list.mapToGlobal(pos))  # type: ignore[arg-type]

    def _delete_family_by_key(self, family_key: str):  # type: ignore[return]
        def _action() -> None:
            entries = [e for e in self.catalog_entries() if e.family_key == family_key and e.is_command]
            count = len(entries)
            if not count:
                QMessageBox.information(self, "Empty family", f"No commands found in family '{family_key}'.")  # type: ignore[arg-type]
                return
            reply = QMessageBox.question(
                self,  # type: ignore[arg-type]
                "Delete family",
                f"Delete family '{family_key}' and all {count} commands in it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            deleted = 0
            for entry in entries:
                if entry.command_id is not None:
                    self.manager.repository.command_store.delete_command(entry.command_id)
                    deleted += 1
            self.manager.update_search_results()
            self.refresh_entries()
            self.manager.show_status(f"Deleted {deleted} commands from family '{family_key}'.")
        return _action
