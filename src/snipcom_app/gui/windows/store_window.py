from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from ...core.repository import SnipcomEntry
from ...core.snip_types import SNIP_TYPE_LABELS
from .store_actions import StoreActionsMixin
from .store_import import StoreImportMixin
from .store_sources import StoreSourcesMixin

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class StoreWindow(StoreActionsMixin, StoreImportMixin, StoreSourcesMixin, QMainWindow):
    def __init__(self, manager: "NoteCopyPaster") -> None:
        super().__init__(manager)
        self.manager = manager
        self.entries_by_id: dict[str, SnipcomEntry] = {}
        self.setWindowTitle("Snipcom Store")
        self.resize(980, 620)

        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        import_layout = QHBoxLayout()
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(8)

        import_menu_btn = QPushButton("Import ▼")
        import_menu = QMenu(self)
        import_menu.addAction("Navi Cheats from File/Folder...", lambda: self._import_from_file("navi-cheat"))
        import_menu.addAction("Cheatsheets from File/Folder...", lambda: self._import_from_file("cheatsheet"))
        import_menu.addAction("JSON Pack from File...", lambda: self._import_from_file("json-pack"))
        import_menu.addSeparator()
        import_menu.addAction("Local Navi Repo", lambda: self.import_local_preset("local-navi"))
        import_menu.addAction("Local Cheatsheets Repo", lambda: self.import_local_preset("local-cheatsheets"))
        import_menu_btn.setMenu(import_menu)
        import_layout.addWidget(import_menu_btn)

        self.export_button = QPushButton("Export Visible...")
        self.export_button.clicked.connect(self.export_visible_entries)
        import_layout.addWidget(self.export_button)

        update_menu_btn = QPushButton("Update ▼")
        update_menu = QMenu(self)
        update_menu.addAction("Sync Selected Source", self.refresh_selected_source)
        update_menu.addAction("Sync All Sources", self.refresh_all_sources)
        update_menu_btn.setMenu(update_menu)
        import_layout.addWidget(update_menu_btn)

        self.recommended_repositories_button = QPushButton("Recommended Repositories...")
        self.recommended_repositories_button.clicked.connect(self.import_recommended_repositories)
        import_layout.addWidget(self.recommended_repositories_button)

        import_layout.addStretch(1)
        root_layout.addLayout(import_layout)

        github_row = QHBoxLayout()
        github_row.setContentsMargins(0, 0, 0, 0)
        github_row.setSpacing(8)
        github_row.addWidget(QLabel("GitHub URL:"))
        self.github_url_input = QLineEdit()
        self.github_url_input.setPlaceholderText("https://github.com/user/repo.git")
        github_row.addWidget(self.github_url_input, 1)
        self.github_kind_combo = QComboBox()
        self.github_kind_combo.addItem("Navi Cheats (.cheat)", "navi-cheat")
        self.github_kind_combo.addItem("Cheatsheets", "cheatsheet")
        github_row.addWidget(self.github_kind_combo)
        self.add_github_button = QPushButton("Add & Install")
        self.add_github_button.clicked.connect(self.add_github_repo)
        github_row.addWidget(self.add_github_button)
        self.manage_sources_button = QPushButton("Manage Sources...")
        self.manage_sources_button.clicked.connect(self.manage_sources_dialog)
        github_row.addWidget(self.manage_sources_button)
        root_layout.addLayout(github_row)

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search command names, tags, families, descriptions, and content...")
        self.search_input.textChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.search_input, 1)

        self.scope_filter = QComboBox()
        self.scope_filter.addItem("Catalog + Workflow", "all")
        self.scope_filter.addItem("Catalog Only", "catalog")
        self.scope_filter.addItem("Workflow Only", "workflow")
        self.scope_filter.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.scope_filter)

        self.snip_type_filter = QComboBox()
        self.snip_type_filter.addItem("All Types", "all")
        self.snip_type_filter.addItem("Family commands", "family_command")
        self.snip_type_filter.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.snip_type_filter)

        self.family_filter = QComboBox()
        self.family_filter.addItem("All Families", "")
        self.family_filter.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.family_filter)

        self.family_pin_filter = QComboBox()
        self.family_pin_filter.addItem("All Family States", "all")
        self.family_pin_filter.addItem("Pinned Families", "pinned")
        self.family_pin_filter.addItem("Unpinned Families", "unpinned")
        self.family_pin_filter.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.family_pin_filter)

        self.batch_filter = QComboBox()
        self.batch_filter.addItem("All Batches", 0)
        self.batch_filter.currentIndexChanged.connect(self.refresh_entries)
        controls_layout.addWidget(self.batch_filter)

        root_layout.addLayout(controls_layout)

        self.summary_label = QLabel("Command catalog")
        root_layout.addWidget(self.summary_label)

        splitter = QSplitter()
        root_layout.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.family_list = QListWidget()
        self.family_list.setMaximumHeight(170)
        self.family_list.currentItemChanged.connect(self.handle_family_list_selection)
        self.family_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.family_list.customContextMenuRequested.connect(self._show_family_context_menu)
        left_layout.addWidget(self.family_list)

        self.entry_list = QListWidget()
        self.entry_list.currentItemChanged.connect(self.update_preview)
        self.entry_list.itemDoubleClicked.connect(self.open_selected_entry)
        self.entry_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.entry_list.customContextMenuRequested.connect(self._show_entry_context_menu)
        left_layout.addWidget(self.entry_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        right_layout.addWidget(self.preview, 1)

        pin_row = QHBoxLayout()
        pin_row.setContentsMargins(0, 0, 0, 0)
        pin_row.setSpacing(8)
        self.pin_family_button = QPushButton("Pin Family")
        self.pin_family_button.clicked.connect(self.toggle_selected_family_pin)
        pin_row.addWidget(self.pin_family_button)
        pin_row.addStretch(1)
        right_layout.addLayout(pin_row)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)

        self.setCentralWidget(central)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1600)
        self.refresh_timer.timeout.connect(self.refresh_entries)
        self.refresh_timer.start()

        self.refresh_entries()

    def catalog_entries(self) -> list[SnipcomEntry]:
        scope = str(self.scope_filter.currentData())
        if scope == "catalog":
            return self.manager.repository.catalog_entries(include_active_commands=False)
        if scope == "workflow":
            return [entry for entry in self.manager.active_entries() if entry.is_command]
        return self.manager.repository.catalog_entries(include_active_commands=True)

    def refresh_family_filter(self, entries: list[SnipcomEntry]) -> None:
        current_value = self.family_filter.currentData()
        families = sorted({entry.family_key for entry in entries if entry.family_key.strip()}, key=str.casefold)
        self.family_filter.blockSignals(True)
        self.family_filter.clear()
        self.family_filter.addItem("All Families", "")
        for family in families:
            self.family_filter.addItem(family, family)
        index = max(0, self.family_filter.findData(current_value))
        self.family_filter.setCurrentIndex(index)
        self.family_filter.blockSignals(False)

    def refresh_family_list(self, entries: list[SnipcomEntry]) -> None:
        current_value = str(self.family_filter.currentData() or "")
        counts: dict[str, int] = {}
        for entry in entries:
            if not entry.family_key:
                continue
            counts[entry.family_key] = counts.get(entry.family_key, 0) + 1

        self.family_list.blockSignals(True)
        self.family_list.clear()
        all_item = QListWidgetItem(f"All Families ({sum(counts.values())})")
        all_item.setData(0x0100, "")
        self.family_list.addItem(all_item)
        for family in sorted(counts, key=str.casefold):
            label = f"{family} ({counts[family]})"
            if self.manager.is_pinned_family(family):
                label += " [Pinned]"
            item = QListWidgetItem(label)
            item.setData(0x0100, family)
            self.family_list.addItem(item)

        restore_row = 0
        for index in range(self.family_list.count()):
            item = self.family_list.item(index)
            if str(item.data(0x0100) or "") == current_value:
                restore_row = index
                break
        self.family_list.setCurrentRow(restore_row)
        self.family_list.blockSignals(False)

    def refresh_batch_filter(self) -> None:
        current_value = self.batch_filter.currentData()
        batches = self.manager.repository.list_import_batches()
        self.batch_filter.blockSignals(True)
        self.batch_filter.clear()
        self.batch_filter.addItem("All Batches", 0)
        self.batch_filter.addItem("No Batch", -1)
        for batch in batches:
            self.batch_filter.addItem(str(batch["label"]), int(batch["id"]))
        index = max(0, self.batch_filter.findData(current_value))
        self.batch_filter.setCurrentIndex(index)
        self.batch_filter.blockSignals(False)

    def filtered_entries(self) -> list[SnipcomEntry]:
        entries = self.catalog_entries()
        self.refresh_family_filter(entries)
        self.refresh_family_list(entries)
        self.refresh_batch_filter()

        query = self.search_input.text().strip().casefold()
        snip_type_filter = str(self.snip_type_filter.currentData())
        family_filter = str(self.family_filter.currentData() or "")
        family_pin_filter = str(self.family_pin_filter.currentData() or "all")
        batch_filter = int(self.batch_filter.currentData() or 0)

        filtered: list[SnipcomEntry] = []
        scored_filtered: list[tuple[int, SnipcomEntry]] = []
        usage_counts = self.manager.repository.command_store.usage_counts()
        for entry in entries:
            if snip_type_filter != "all" and entry.snip_type != snip_type_filter:
                continue
            if family_filter and entry.family_key != family_filter:
                continue
            if family_pin_filter == "pinned" and not self.manager.is_pinned_family(entry.family_key):
                continue
            if family_pin_filter == "unpinned" and entry.family_key and self.manager.is_pinned_family(entry.family_key):
                continue
            if batch_filter > 0 and entry.import_batch_id != batch_filter:
                continue
            if batch_filter == -1 and entry.import_batch_id != 0:
                continue
            if query:
                haystacks = [
                    entry.display_name.casefold(),
                    entry.tag_text.casefold(),
                    entry.family_key.casefold(),
                    entry.source_kind.casefold(),
                    entry.source_license.casefold(),
                ]
                content = self.manager.read_entry_text_quiet(entry)
                if content:
                    haystacks.append(content.casefold())
                if not any(query in haystack for haystack in haystacks):
                    continue
                score = self.manager.command_search_score(
                    entry,
                    query,
                    content or "",
                    usage_count=usage_counts.get(entry.command_id or -1, 0),
                )
                scored_filtered.append((score, entry))
                continue
            filtered.append(entry)

        if query:
            return [entry for _score, entry in sorted(scored_filtered, key=lambda item: (-item[0], item[1].display_name.casefold(), item[1].entry_id))]
        filtered.sort(key=lambda entry: (entry.display_name.casefold(), entry.entry_id))
        return filtered

    def refresh_entries(self) -> None:
        current_entry_id = ""
        current_item = self.entry_list.currentItem()
        if current_item is not None:
            current_entry_id = str(current_item.data(0x0100))

        entries = self.filtered_entries()
        self.entries_by_id = {entry.entry_id: entry for entry in entries}

        self.entry_list.blockSignals(True)
        self.entry_list.clear()
        for entry in entries:
            parts = [entry.display_name, SNIP_TYPE_LABELS.get(entry.snip_type, entry.snip_type)]
            if entry.family_key:
                parts.append(entry.family_key)
                if self.manager.is_pinned_family(entry.family_key):
                    parts.append("pinned")
            if entry.catalog_only:
                parts.append("catalog")
            else:
                parts.append("workflow")
            if entry.tag_text:
                parts.append(entry.tag_text)
            item = QListWidgetItem(" | ".join(parts))
            item.setData(0x0100, entry.entry_id)
            if entry.dangerous:
                item.setForeground(QColor(255, 188, 104))
            self.entry_list.addItem(item)

        restore_index = -1
        if current_entry_id:
            for index in range(self.entry_list.count()):
                item = self.entry_list.item(index)
                if str(item.data(0x0100)) == current_entry_id:
                    restore_index = index
                    break
        if restore_index >= 0:
            self.entry_list.setCurrentRow(restore_index)
        elif self.entry_list.count() > 0:
            self.entry_list.setCurrentRow(0)
        self.entry_list.blockSignals(False)

        catalog_count = sum(1 for entry in entries if entry.catalog_only)
        workflow_count = len(entries) - catalog_count
        self.summary_label.setText(
            f"{len(entries)} visible commands | {catalog_count} catalog | {workflow_count} workflow | pinned families: {', '.join(sorted(self.manager.pinned_families)) or '-'}"
        )
        self.update_preview()

    def handle_family_list_selection(self) -> None:
        current_item = self.family_list.currentItem()
        if current_item is None:
            return
        family_key = str(current_item.data(0x0100) or "")
        index = self.family_filter.findData(family_key)
        if index >= 0 and index != self.family_filter.currentIndex():
            self.family_filter.setCurrentIndex(index)

    def selected_entry(self) -> SnipcomEntry | None:
        current_item = self.entry_list.currentItem()
        if current_item is None:
            return None
        entry_id = str(current_item.data(0x0100))
        return self.entries_by_id.get(entry_id)

    def update_preview(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.preview.setPlainText("No command selected.")
            self.pin_family_button.setText("Pin Family")
            self.pin_family_button.setEnabled(False)
            return

        content = self.manager.read_entry_text_quiet(entry) or ""
        lines = [
            f"Name: {entry.display_name}",
            f"Type: {SNIP_TYPE_LABELS.get(entry.snip_type, entry.snip_type)}",
            f"Scope: {'Catalog' if entry.catalog_only else 'Workflow'}",
            f"Family: {entry.family_key or '-'}",
            f"Family pinned: {'yes' if self.manager.is_pinned_family(entry.family_key) else 'no'}",
            f"Tags: {entry.tag_text or '-'}",
            f"Source: {entry.source_kind or '-'}",
            f"Source Ref: {entry.source_ref or '-'}",
            f"License: {entry.source_license or '-'}",
            f"Import Batch: {entry.import_batch_id or '-'}",
            f"Dangerous: {'yes' if entry.dangerous else 'no'}",
        ]
        if entry.command_id is not None:
            try:
                record = self.manager.repository.command_store.get_command(entry.command_id)
            except KeyError:
                record = None
            if record is not None and record.description.strip():
                lines.append(f"Description: {record.description.strip()}")
        lines.extend(["", content])
        if entry.command_id is not None:
            related_ids = self.manager.repository.command_store.related_command_ids(entry.command_id, limit=5)
            if related_ids:
                related_entries: list[str] = []
                for related_id in related_ids:
                    related_entry = self.manager.repository.entry_from_id(
                        self.manager.repository.command_entry_id(related_id),
                        self.manager.tags,
                        self.manager.snip_types,
                    )
                    if related_entry is not None:
                        related_entries.append(related_entry.display_name)
                if related_entries:
                    lines.extend(["", "Related commands:", *[f"- {label}" for label in related_entries]])
        self.preview.setPlainText("\n".join(lines))
        self.pin_family_button.setText("Unpin Family" if self.manager.is_pinned_family(entry.family_key) else "Pin Family")
        self.pin_family_button.setEnabled(bool(entry.family_key))



PlaceholderStoreWindow = StoreWindow
