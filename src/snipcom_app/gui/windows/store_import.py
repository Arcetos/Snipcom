from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...integration.import_source_catalog import (
    IMPORT_SOURCE_OPTIONS,
    LOCAL_PRESET_SOURCES,
    RECOMMENDED_REPOSITORIES,
    repository_badge_color,
    repository_size_badge,
)
from ...integration.importers import (
    ImportBatchPayload,
    export_internal_json_pack,
    import_cheatsheets,
    import_internal_json_pack,
    import_navi_cheats,
    import_tldr_pages,
)
from ...integration.source_sync import upsert_import_payload

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class StoreImportMixin:
    """Mixin providing import/export orchestration for StoreWindow."""

    manager: "NoteCopyPaster"

    # These are provided by StoreWindow (declared here for type-checking only)
    def filtered_entries(self): ...  # type: ignore[empty-body]
    def refresh_entries(self) -> None: ...  # type: ignore[empty-body]

    def _import_from_file(self, source_key: str) -> None:
        try:
            payload = self.load_import_payload(source_key)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))  # type: ignore[arg-type]
            return
        if payload is None:
            return
        if not payload.commands:
            QMessageBox.information(self, "Nothing imported", "No usable commands were found in that source.")  # type: ignore[arg-type]
            return
        imported = self.import_payload_commands(payload)
        self.manager.show_status(f"Imported {imported} commands into the store catalog.")
        self.manager.update_search_results()
        self.refresh_entries()
        QMessageBox.information(self, "Import finished", f"Imported {imported} commands into the catalog.")  # type: ignore[arg-type]

    def import_local_preset(self, preset_key: str) -> None:
        preset = LOCAL_PRESET_SOURCES.get(preset_key)
        if preset is None:
            return
        source_path = Path(preset["path"])
        if not source_path.exists():
            QMessageBox.warning(self, "Preset missing", f"{source_path} is not available on this machine.")  # type: ignore[arg-type]
            return
        try:
            if str(preset["source_kind"]) == "navi-cheat":
                payload = import_navi_cheats(source_path, source_license=str(preset["license"]))
            else:
                payload = import_cheatsheets(source_path, source_license=str(preset["license"]))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import failed", str(exc))  # type: ignore[arg-type]
            return
        if not payload.commands:
            QMessageBox.information(self, "Nothing imported", "No usable commands were found in that preset source.")  # type: ignore[arg-type]
            return

        imported = self.import_payload_commands(payload, source_ref_override=str(source_path), label_override=str(preset["label"]))

        self.manager.show_status(f"Imported {imported} commands from {preset['label']}.")
        self.manager.update_search_results()
        self.refresh_entries()
        QMessageBox.information(self, "Import finished", f"Imported {imported} commands from {preset['label']}.")  # type: ignore[arg-type]

    def import_recommended_repositories(self) -> None:
        selected_sources = self.select_recommended_repositories()
        if not selected_sources:
            return
        if not self.confirm_recommended_import(selected_sources):
            return

        from ...integration.source_sync import sync_import_source

        # Show a non-closeable progress dialog; run the sync in a background thread
        # so the UI stays responsive during git clone + large DB upserts.
        wait_dlg = QDialog(self)  # type: ignore[arg-type]
        wait_dlg.setWindowTitle("Importing Repositories")
        wait_dlg.setModal(True)
        wait_dlg.setFixedSize(380, 80)
        _vl = QVBoxLayout(wait_dlg)
        _vl.setContentsMargins(18, 16, 18, 16)
        _status_label = QLabel("Cloning and importing, please wait...")
        _status_label.setWordWrap(True)
        _vl.addWidget(_status_label)

        _results: dict[str, object] = {
            "done": False, "summaries": [], "failed": [], "created": 0, "updated": 0,
        }

        def _run() -> None:
            summaries: list[str] = []
            failed: list[str] = []
            created_total = 0
            updated_count = 0
            for source in selected_sources:
                try:
                    source_record = self.manager.repository.upsert_import_source(
                        name=str(source["name"]),
                        kind=str(source["source_kind"]),
                        path_or_url=str(source["url"]),
                        is_git=True,
                    )
                    result = sync_import_source(
                        self.manager.repository,
                        source_id=source_record.source_id,
                        app_support_dir=self.manager.profile_manager.app_support_dir,
                    )
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"{str(source['name'])}: {exc}")
                    continue
                updated_count += int(result["updated"])
                created_total += int(result["created"])
                summaries.append(
                    f"{str(source['name'])}: created {int(result['created'])}, "
                    f"updated {int(result['updated'])}, skipped {int(result['skipped'])}"
                )
            _results["summaries"] = summaries
            _results["failed"] = failed
            _results["created"] = created_total
            _results["updated"] = updated_count
            _results["done"] = True

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()

        poll_timer = QTimer()
        poll_timer.setInterval(300)

        def _check_done() -> None:
            if _results["done"]:
                poll_timer.stop()
                wait_dlg.accept()

        poll_timer.timeout.connect(_check_done)
        poll_timer.start()
        wait_dlg.exec()

        # Back on main thread — update UI
        self.manager.update_search_results()
        self.refresh_entries()

        import_summaries: list[str] = list(_results["summaries"])  # type: ignore[arg-type]
        failed: list[str] = list(_results["failed"])  # type: ignore[arg-type]
        created_total = int(_results["created"])
        updated_count = int(_results["updated"])

        if import_summaries:
            self.manager.show_status(
                f"Imported recommended repositories: {created_total} created, {updated_count} updated."
            )
        if failed:
            details = "\n".join(import_summaries + ["", "Errors:"] + failed)
            QMessageBox.warning(self, "Recommended import completed with errors", details.strip())  # type: ignore[arg-type]
            return
        if import_summaries:
            QMessageBox.information(self, "Recommended import complete", "\n".join(import_summaries))  # type: ignore[arg-type]

    def select_recommended_repositories(self) -> list[dict[str, object]]:
        dialog = QDialog(self)  # type: ignore[arg-type]
        dialog.setWindowTitle("Recommended Repositories")
        dialog.resize(720, 460)

        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Select one or more curated repositories to clone and import into the command catalog. "
            "Badges indicate approximate pack size."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        repo_list = QListWidget(dialog)
        for repo in RECOMMENDED_REPOSITORIES:
            estimated = int(repo.get("estimated_commands", 0) or 0)
            badge = repository_size_badge(estimated)
            item = QListWidgetItem(f"{str(repo['name'])} [{str(repo['source_kind'])}] [{badge} ~{estimated}]")
            item.setForeground(repository_badge_color(badge))
            item.setData(0x0100, repo["key"])
            item.setToolTip(f"{str(repo['url'])}\n{str(repo['description'])}")
            repo_list.addItem(item)
        repo_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(repo_list, 1)

        details_label = QLabel("Select a repository to see details.")
        details_label.setWordWrap(True)
        layout.addWidget(details_label)

        button_row = QHBoxLayout()
        import_selected_button = QPushButton("Import Selected")
        cancel_button = QPushButton("Cancel")
        button_row.addWidget(import_selected_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        selected_keys: list[str] = []

        def selected_repos() -> list[dict[str, object]]:
            repos: list[dict[str, object]] = []
            for item in repo_list.selectedItems():
                key = str(item.data(0x0100))
                repo = next((payload for payload in RECOMMENDED_REPOSITORIES if payload["key"] == key), None)
                if repo is not None:
                    repos.append(repo)
            return repos

        def update_details() -> None:
            repos = selected_repos()
            if not repos:
                current = repo_list.currentItem()
                if current is None:
                    details_label.setText("Select a repository to see details.")
                    return
                key = str(current.data(0x0100))
                repo = next((payload for payload in RECOMMENDED_REPOSITORIES if payload["key"] == key), None)
                if repo is None:
                    details_label.setText("Select a repository to see details.")
                    return
                estimated = int(repo.get("estimated_commands", 0) or 0)
                badge = repository_size_badge(estimated)
                details_label.setText(
                    f"{str(repo['name'])} [{badge} ~{estimated}]\n"
                    f"{str(repo['description'])}\n\n"
                    f"Source: {str(repo['url'])}\nLicense: {str(repo.get('license', '') or '-')}"
                )
                return
            estimated_total = sum(int(repo.get("estimated_commands", 0) or 0) for repo in repos)
            details_lines = [
                f"{str(repo['name'])} [{repository_size_badge(int(repo.get('estimated_commands', 0) or 0))} "
                f"~{int(repo.get('estimated_commands', 0) or 0)}] -> {str(repo['url'])}"
                for repo in repos
            ]
            details_label.setText("Selected:\n" + "\n".join(details_lines))
            details_label.setText(details_label.text() + f"\n\nEstimated total commands: ~{estimated_total}")

        def accept_selected() -> None:
            nonlocal selected_keys
            repos = selected_repos()
            if not repos:
                QMessageBox.information(dialog, "Select repositories", "Select at least one repository.")
                return
            selected_keys = [repo["key"] for repo in repos]
            dialog.accept()

        repo_list.itemSelectionChanged.connect(update_details)
        repo_list.currentItemChanged.connect(lambda *_: update_details())
        import_selected_button.clicked.connect(accept_selected)
        cancel_button.clicked.connect(dialog.reject)
        update_details()

        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return []
        return [repo for repo in RECOMMENDED_REPOSITORIES if repo["key"] in selected_keys]

    def confirm_recommended_import(self, selected_sources: list[dict[str, object]]) -> bool:
        estimated_total = sum(int(source.get("estimated_commands", 0) or 0) for source in selected_sources)
        lines = [
            f"- {str(source['name'])} ({repository_size_badge(int(source.get('estimated_commands', 0) or 0))}, "
            f"~{int(source.get('estimated_commands', 0) or 0)} commands)"
            for source in selected_sources
        ]
        message = (
            "The selected repositories will be cloned or updated and then imported into the catalog.\n\n"
            + "\n".join(lines)
            + f"\n\nEstimated combined command volume: ~{estimated_total}\n\nContinue?"
        )
        choice = QMessageBox.question(
            self,  # type: ignore[arg-type]
            "Confirm Recommended Import",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return choice == QMessageBox.StandardButton.Yes

    def import_payload_commands(
        self,
        payload: ImportBatchPayload,
        *,
        source_ref_override: str | None = None,
        label_override: str | None = None,
    ) -> int:
        source_name = (label_override or payload.label).strip()
        source_ref = source_ref_override if source_ref_override is not None else payload.source_ref
        source_id = 0
        if source_name and source_ref:
            source = self.manager.repository.upsert_import_source(
                name=source_name,
                kind=payload.source_kind,
                path_or_url=source_ref,
                is_git=source_ref.strip().endswith(".git"),
            )
            source_id = source.source_id

        result = upsert_import_payload(
            self.manager.repository,
            payload,
            source_ref_override=source_ref if source_ref else source_ref_override,
            label_override=label_override,
            source_id=source_id,
            source_name=source_name,
        )
        if source_id > 0:
            self.manager.repository.update_import_source(
                source_id,
                last_sync_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                last_status="ok",
                last_batch_id=int(result["batch_id"]),
            )
        return int(result["created"]) + int(result["updated"])

    def load_import_payload(self, source_key: str) -> ImportBatchPayload | None:
        if source_key == "json-pack":
            file_name, _ = QFileDialog.getOpenFileName(
                self,  # type: ignore[arg-type]
                "Import Snipcom JSON Pack",
                str(Path.home()),
                "JSON files (*.json)",
            )
            if not file_name:
                return None
            return import_internal_json_pack(Path(file_name))

        selected_path = QFileDialog.getExistingDirectory(self, "Choose Import Folder", str(Path.home()))  # type: ignore[arg-type]
        if not selected_path:
            file_name, _ = QFileDialog.getOpenFileName(self, "Choose Import File", str(Path.home()), "All files (*)")  # type: ignore[arg-type]
            if not file_name:
                return None
            selected_path = file_name

        source_path = Path(selected_path)
        source_license = str(IMPORT_SOURCE_OPTIONS.get(source_key, {}).get("license", ""))
        if source_key == "navi-cheat":
            return import_navi_cheats(source_path, source_license=source_license)
        if source_key == "cheatsheet":
            return import_cheatsheets(source_path, source_license=source_license)
        if source_key == "tldr-pages":
            return import_tldr_pages(source_path, source_license=source_license)
        raise ValueError("Unsupported import source.")

    def export_visible_entries(self) -> None:
        entries = self.filtered_entries()
        if not entries:
            QMessageBox.information(self, "Nothing to export", "There are no visible commands to export.")  # type: ignore[arg-type]
            return
        file_name, _ = QFileDialog.getSaveFileName(
            self,  # type: ignore[arg-type]
            "Export Visible Commands",
            str(Path.home() / "snipcom-export.json"),
            "JSON files (*.json)",
        )
        if not file_name:
            return

        commands: list[dict[str, object]] = []
        for entry in entries:
            if not entry.is_command or entry.command_id is None:
                continue
            record = self.manager.repository.command_store.get_command(entry.command_id)
            commands.append(
                {
                    "title": record.title,
                    "body": record.body,
                    "snip_type": record.snip_type,
                    "family_key": record.family_key,
                    "description": record.description,
                    "tags": list(record.tags),
                    "source_kind": record.source_kind,
                    "source_ref": record.source_ref,
                    "source_license": record.source_license,
                    "extra": dict(record.extra),
                }
            )

        export_internal_json_pack(
            Path(file_name),
            commands,
            label="Snipcom export",
            source_license="mixed",
        )
        self.manager.show_status(f"Exported {len(commands)} visible commands.")
