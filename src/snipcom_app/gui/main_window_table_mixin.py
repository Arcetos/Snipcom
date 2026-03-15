from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowTableMixin:
    def default_column_width_map(self: "NoteCopyPaster") -> dict[int, int]:
        columns = getattr(self, "table_columns", ["name", "family", "tag", "modified", "actions"])
        viewport_width = max(1, self.table.viewport().width())
        min_section = self.table.horizontalHeader().minimumSectionSize()

        family_width = max(self.scaled_size(96), min_section)
        tag_width = max(self.scaled_size(88), min_section)
        modified_width = max(
            self.scaled_size(150),
            self.table.fontMetrics().horizontalAdvance("2026-03-08 03:26") + self.scaled_size(20),
        )

        actions_col = columns.index("actions") if "actions" in columns else None
        actions_width = self.scaled_size(330)
        if self.table.rowCount() > 0 and actions_col is not None:
            actions_widget = self.table.cellWidget(0, actions_col)
            if actions_widget is not None:
                actions_width = max(self.scaled_size(280), actions_widget.sizeHint().width() + self.scaled_size(8))

        key_widths: dict[str, int] = {
            "family": family_width,
            "tag": tag_width,
            "modified": modified_width,
            "actions": actions_width,
        }
        non_name_total = sum(key_widths.get(key, self.scaled_size(100)) for key in columns if key != "name")
        key_widths["name"] = max(self.scaled_size(180), viewport_width - non_name_total)

        return {i: key_widths.get(key, self.scaled_size(100)) for i, key in enumerate(columns)}

    def minimum_column_width_map(self: "NoteCopyPaster") -> dict[int, int]:
        columns = getattr(self, "table_columns", ["name", "family", "tag", "modified", "actions"])
        default_widths = self.default_column_width_map()
        minimum_section = self.table.horizontalHeader().minimumSectionSize()
        result: dict[int, int] = {}
        for i, key in enumerate(columns):
            width = default_widths.get(i, self.scaled_size(100))
            if key == "actions":
                # Actions column must stay wide enough for its buttons
                result[i] = max(minimum_section, round(width * 0.75))
            else:
                result[i] = max(minimum_section, round(width * 0.3))
        return result

    def fitted_column_widths(
        self: "NoteCopyPaster",
        source_widths: dict[int, int],
        minimum_widths: dict[int, int],
        total_width: int,
    ) -> dict[int, int]:
        logical_columns = sorted(source_widths)
        minimum_total = sum(minimum_widths[logical] for logical in logical_columns)
        if total_width <= minimum_total:
            return {
                logical: max(1, source_widths[logical])
                for logical in logical_columns
            }

        remaining = set(logical_columns)
        widths = {logical: 0 for logical in logical_columns}
        remaining_width = total_width
        remaining_source = float(sum(max(1, source_widths[logical]) for logical in remaining))

        while remaining:
            changed = False
            for logical in list(remaining):
                source_width = max(1, source_widths[logical])
                ideal_width = remaining_width * source_width / remaining_source if remaining_source else remaining_width / len(remaining)
                if ideal_width < minimum_widths[logical]:
                    widths[logical] = minimum_widths[logical]
                    remaining_width -= widths[logical]
                    remaining_source -= source_width
                    remaining.remove(logical)
                    changed = True
            if not changed:
                break

        if remaining:
            remaining_source = float(sum(max(1, source_widths[logical]) for logical in remaining))
            for logical in remaining:
                source_width = max(1, source_widths[logical])
                widths[logical] = max(
                    minimum_widths[logical],
                    round(remaining_width * source_width / remaining_source) if remaining_source else 0,
                )

        difference = total_width - sum(widths.values())
        if difference != 0:
            adjustable = sorted(logical_columns, key=lambda logical: source_widths[logical], reverse=difference > 0)
            step = 1 if difference > 0 else -1
            while difference != 0 and adjustable:
                changed = False
                for logical in adjustable:
                    proposed = widths[logical] + step
                    if proposed < minimum_widths[logical]:
                        continue
                    widths[logical] = proposed
                    difference -= step
                    changed = True
                    if difference == 0:
                        break
                if not changed:
                    break

        return widths

    def apply_saved_column_order(self: "NoteCopyPaster") -> None:
        order = self.settings.get("column_order")
        header = self.table.horizontalHeader()
        if not isinstance(order, list) or len(order) != header.count():
            return

        try:
            desired_order = [int(logical) for logical in order]
        except (TypeError, ValueError):
            return

        if sorted(desired_order) != list(range(header.count())):
            return

        self.updating_column_layout = True
        try:
            for visual_index, logical in enumerate(desired_order):
                current_visual = header.visualIndex(logical)
                if current_visual != visual_index:
                    header.moveSection(current_visual, visual_index)
        finally:
            self.updating_column_layout = False

    def restore_default_column_order(self: "NoteCopyPaster") -> None:
        header = self.table.horizontalHeader()
        self.updating_column_layout = True
        try:
            for logical in range(header.count()):
                current_visual = header.visualIndex(logical)
                if current_visual != logical:
                    header.moveSection(current_visual, logical)
        finally:
            self.updating_column_layout = False

    def update_tag_header_filter_button(self: "NoteCopyPaster") -> None:
        columns = getattr(self, "table_columns", ["name", "family", "tag", "modified", "actions"])
        if "tag" not in columns:
            self.tag_filter_header_button.hide()
            return
        header = self.table.horizontalHeader()
        logical_index = columns.index("tag")
        x = header.sectionViewportPosition(logical_index)
        width = header.sectionSize(logical_index)
        button_size = self.scaled_size(16)
        if width < button_size + self.scaled_size(14):
            self.tag_filter_header_button.hide()
            return

        self.tag_filter_header_button.setIconSize(QSize(button_size, button_size))
        y = max(0, (header.height() - button_size) // 2)
        self.tag_filter_header_button.setGeometry(
            x + width - button_size - self.scaled_size(6),
            y,
            button_size,
            button_size,
        )
        self.tag_filter_header_button.raise_()
        self.tag_filter_header_button.show()

    def sync_table_columns_to_viewport(self: "NoteCopyPaster") -> None:
        if self.updating_column_layout:
            return

        viewport_width = self.table.viewport().width()
        if viewport_width <= 0:
            return

        default_widths = self.default_column_width_map()
        minimum_widths = self.minimum_column_width_map()
        saved_widths = self.settings.get("column_widths")
        source_widths = default_widths
        if isinstance(saved_widths, list) and len(saved_widths) == self.table.columnCount():
            cleaned_widths: dict[int, int] = {}
            for logical, width in enumerate(saved_widths):
                try:
                    cleaned_widths[logical] = max(1, int(width))
                except (TypeError, ValueError):
                    cleaned_widths = {}
                    break
            if cleaned_widths:
                source_widths = cleaned_widths
        elif self.columns_initialized:
            source_widths = {
                logical: max(1, self.table.columnWidth(logical))
                for logical in range(self.table.columnCount())
            }

        fitted_widths = self.fitted_column_widths(source_widths, minimum_widths, viewport_width)
        self.updating_column_layout = True
        try:
            for logical, width in fitted_widths.items():
                self.table.setColumnWidth(logical, width)
        finally:
            self.updating_column_layout = False

        self.columns_initialized = True
        self.update_tag_header_filter_button()
        self.save_runtime_preferences()

    def handle_column_resized(self: "NoteCopyPaster", _logical_index: int, _old_size: int, _new_size: int) -> None:
        if self.table.columnCount() == 0 or self.updating_column_layout:
            return
        self.columns_initialized = True
        self.update_tag_header_filter_button()
        self.save_runtime_preferences()

    def handle_column_moved(self: "NoteCopyPaster", _logical: int, _old_visual_index: int, _new_visual_index: int) -> None:
        if self.updating_column_layout:
            return
        self.update_tag_header_filter_button()
        self.save_runtime_preferences()

    def apply_default_column_widths(self: "NoteCopyPaster") -> None:
        self.sync_table_columns_to_viewport()
