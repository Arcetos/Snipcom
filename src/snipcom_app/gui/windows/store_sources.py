from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...integration.source_sync import sync_import_source

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class StoreSourcesMixin:
    """Mixin providing source sync and management methods for StoreWindow."""

    manager: "NoteCopyPaster"

    # These are provided by StoreWindow (declared here for type-checking only)
    def selected_entry(self): ...  # type: ignore[empty-body]
    def refresh_entries(self) -> None: ...  # type: ignore[empty-body]

    def refresh_selected_source(self) -> None:
        entry = self.selected_entry()
        if entry is None or not entry.is_command or entry.command_id is None:
            QMessageBox.information(self, "Select source", "Select a command entry that belongs to a registered source.")  # type: ignore[arg-type]
            return
        try:
            record = self.manager.repository.command_store.get_command(entry.command_id)
        except KeyError:
            self.refresh_entries()
            return
        source_id = int(record.extra.get("source_id", 0) or 0)
        if source_id <= 0:
            QMessageBox.information(self, "No source", "The selected entry is not tied to a registered import source.")  # type: ignore[arg-type]
            return
        try:
            result = sync_import_source(
                self.manager.repository,
                source_id=source_id,
                app_support_dir=self.manager.profile_manager.app_support_dir,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Refresh failed", str(exc))  # type: ignore[arg-type]
            return
        self.manager.update_search_results()
        self.refresh_entries()
        QMessageBox.information(
            self,  # type: ignore[arg-type]
            "Refresh complete",
            f"{result['name']}: created {result['created']}, updated {result['updated']}, skipped {result['skipped']}.",
        )

    def refresh_all_sources(self) -> None:
        sources = self.manager.repository.list_import_sources()
        if not sources:
            QMessageBox.information(self, "No sources", "No registered import sources were found.")  # type: ignore[arg-type]
            return
        summaries: list[str] = []
        failed: list[str] = []
        for source in sources:
            try:
                result = sync_import_source(
                    self.manager.repository,
                    source_id=source.source_id,
                    app_support_dir=self.manager.profile_manager.app_support_dir,
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{source.name}: {exc}")
                continue
            deleted = int(result.get("deleted", 0))
            deleted_part = f", -{deleted} removed" if deleted else ""
            summaries.append(
                f"{source.name}: +{result['created']} new, ~{result['updated']} updated, "
                f"{result['skipped']} skipped{deleted_part}"
            )
        self.manager.update_search_results()
        self.refresh_entries()
        summary_text = "\n".join(summaries) if summaries else "No sources were updated."
        if failed:
            QMessageBox.warning(
                self,  # type: ignore[arg-type]
                "Update completed with errors",
                f"{summary_text}\n\nErrors:\n" + "\n".join(failed),
            )
            return
        QMessageBox.information(self, "Update complete", summary_text)  # type: ignore[arg-type]

    def add_github_repo(self) -> None:
        from PyQt6.QtWidgets import QComboBox, QLineEdit
        github_url_input: QLineEdit = self.github_url_input  # type: ignore[attr-defined]
        github_kind_combo: QComboBox = self.github_kind_combo  # type: ignore[attr-defined]

        url = github_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Enter a GitHub repository URL.")  # type: ignore[arg-type]
            return
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("git@")):
            QMessageBox.warning(self, "Invalid URL", "Enter a valid repository URL (https:// or git@).")  # type: ignore[arg-type]
            return
        source_kind = str(github_kind_combo.currentData())
        # Derive a display name from the URL path
        clean = url.rstrip("/")
        if clean.endswith(".git"):
            clean = clean[:-4]
        name = clean.split("/")[-1] or clean.split("/")[-2] or "custom-repo"
        # If already registered, offer to sync instead
        for source in self.manager.repository.list_import_sources():
            if source.path_or_url.strip() == url:
                reply = QMessageBox.question(
                    self,  # type: ignore[arg-type]
                    "Already registered",
                    f"This URL is already saved as '{source.name}'.\nSync it now to get the latest updates?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._sync_single_source(source.source_id, source.name)
                return
        try:
            source_record = self.manager.repository.upsert_import_source(
                name=name, kind=source_kind, path_or_url=url, is_git=True,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Registration failed", str(exc))  # type: ignore[arg-type]
            return
        github_url_input.clear()
        self._sync_single_source(source_record.source_id, name)

    def _sync_single_source(self, source_id: int, name: str) -> None:
        try:
            result = sync_import_source(
                self.manager.repository,
                source_id=source_id,
                app_support_dir=self.manager.profile_manager.app_support_dir,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Sync failed", str(exc))  # type: ignore[arg-type]
            return
        self.manager.update_search_results()
        self.refresh_entries()
        deleted = int(result.get("deleted", 0))
        deleted_part = f", {deleted} removed (no longer in upstream)" if deleted else ""
        QMessageBox.information(
            self,  # type: ignore[arg-type]
            "Repository installed",
            f"'{name}': {result['created']} new, {result['updated']} updated, "
            f"{result['skipped']} skipped{deleted_part}.",
        )

    def manage_sources_dialog(self) -> None:
        dialog = QDialog(self)  # type: ignore[arg-type]
        dialog.setWindowTitle("Manage Saved Sources")
        dialog.resize(760, 420)
        layout = QVBoxLayout(dialog)

        intro = QLabel(
            "All registered import sources. Use 'Sync Selected' to pull the latest changes. "
            "'Remove' unregisters the source; you can also delete all its commands."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        source_list = QListWidget(dialog)
        source_list.setAlternatingRowColors(True)

        def _populate_list() -> None:
            source_list.clear()
            for source in self.manager.repository.list_import_sources():
                last_sync = source.last_sync_at[:10] if source.last_sync_at else "never"
                status_text = source.last_status or "-"
                kind_label = "git" if source.is_git else "local"
                item = QListWidgetItem(
                    f"{source.name}  [{source.kind} / {kind_label}]  "
                    f"last sync: {last_sync}  status: {status_text}\n"
                    f"  {source.path_or_url}"
                )
                item.setData(0x0100, source.source_id)
                if status_text not in ("ok", "-"):
                    item.setForeground(QColor("#C53030"))
                source_list.addItem(item)

        _populate_list()
        layout.addWidget(source_list, 1)

        button_row = QHBoxLayout()
        sync_btn = QPushButton("Sync Selected")
        remove_btn = QPushButton("Remove Selected...")
        button_row.addWidget(sync_btn)
        button_row.addWidget(remove_btn)
        button_row.addStretch(1)
        close_btn = QPushButton("Close")
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        def _selected_source_id() -> int | None:
            item = source_list.currentItem()
            return int(item.data(0x0100)) if item is not None else None

        def sync_selected() -> None:
            sid = _selected_source_id()
            if sid is None:
                QMessageBox.information(dialog, "Select a source", "Select a source first.")
                return
            sources = self.manager.repository.list_import_sources()
            source = next((s for s in sources if s.source_id == sid), None)
            if source is None:
                return
            dialog.setEnabled(False)
            try:
                result = sync_import_source(
                    self.manager.repository,
                    source_id=sid,
                    app_support_dir=self.manager.profile_manager.app_support_dir,
                )
            except Exception as exc:  # noqa: BLE001
                dialog.setEnabled(True)
                QMessageBox.critical(dialog, "Sync failed", str(exc))
                return
            dialog.setEnabled(True)
            self.manager.update_search_results()
            self.refresh_entries()
            _populate_list()
            deleted = int(result.get("deleted", 0))
            deleted_part = f"\n{deleted} stale commands removed." if deleted else ""
            QMessageBox.information(
                dialog, "Sync complete",
                f"'{source.name}': {result['created']} new, {result['updated']} updated, "
                f"{result['skipped']} skipped.{deleted_part}",
            )

        def remove_selected() -> None:
            sid = _selected_source_id()
            if sid is None:
                QMessageBox.information(dialog, "Select a source", "Select a source first.")
                return
            sources = self.manager.repository.list_import_sources()
            source = next((s for s in sources if s.source_id == sid), None)
            if source is None:
                return
            reply = QMessageBox.question(
                dialog,
                "Remove source",
                f"Remove '{source.name}' from saved sources?\n\n"
                f"Also delete all commands imported from this source?\n\n"
                f"Yes = remove source and delete its commands\n"
                f"No = remove source record only (keep commands)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            deleted_cmds = 0
            if reply == QMessageBox.StandardButton.Yes:
                for record in self.manager.repository.command_store.list_commands(
                    catalog_only=True, include_trashed=True
                ):
                    if int(record.extra.get("source_id", 0) or 0) == sid:
                        self.manager.repository.command_store.delete_command(record.command_id)
                        deleted_cmds += 1
            self.manager.repository.delete_import_source(sid)
            self.manager.update_search_results()
            self.refresh_entries()
            _populate_list()
            msg = f"Removed '{source.name}'."
            if deleted_cmds:
                msg += f" Deleted {deleted_cmds} commands."
            self.manager.show_status(msg)

        sync_btn.clicked.connect(sync_selected)
        remove_btn.clicked.connect(remove_selected)
        close_btn.clicked.connect(dialog.accept)
        dialog.exec()
