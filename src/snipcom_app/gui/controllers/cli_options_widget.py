from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from ...core.cli_nav_settings import CliNavSettings

COLUMN_KEY_LABELS: dict[str, str] = {
    "command": "Command",
    "name": "Name",
    "description": "Description",
    "tag": "Tags",
    "family": "Family",
    "dangerous": "Dangerous",
}
COLOR_CHOICES: list[tuple[str, str]] = [
    ("default", "Default terminal"),
    ("black", "Black"),
    ("red", "Red"),
    ("green", "Green"),
    ("yellow", "Yellow"),
    ("blue", "Blue"),
    ("magenta", "Magenta"),
    ("cyan", "Cyan"),
    ("white", "White"),
]
SECTION_COLOR_LABELS: list[tuple[str, str]] = [
    ("input", "Input line"),
    ("workflow", "Workflow rows"),
    ("heuristic", "Heuristic rows"),
    ("ai", "AI rows"),
]

_HEADER_BG = "#1e1e2e"
_HEADER_BORDER = "#44446a"
_HEADER_TEXT = "#88aaff"


class _ColumnCell(QWidget):
    """One column slot in the header bar — a combo + delete button."""

    delete_requested: pyqtSignal = pyqtSignal(object)

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(48)
        self.setStyleSheet(
            f"background: {_HEADER_BG}; border: 1px solid {_HEADER_BORDER}; border-radius: 3px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Top strip: delete button flush right
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch(1)
        del_btn = QPushButton("✕")
        del_btn.setFlat(True)
        del_btn.setFixedSize(16, 16)
        del_btn.setStyleSheet(
            "color: #886688; border: none; background: transparent; font-size: 9px;"
        )
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        top.addWidget(del_btn)
        layout.addLayout(top)

        # Combo centred in the cell
        self._combo = QComboBox()
        self._combo.setFrame(False)
        self._combo.setStyleSheet(
            f"color: {_HEADER_TEXT}; font-weight: bold; background: transparent;"
            " border: none; padding: 0px 2px;"
        )
        for k, lbl in COLUMN_KEY_LABELS.items():
            self._combo.addItem(lbl, userData=k)
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == key:
                self._combo.setCurrentIndex(i)
                break
        layout.addWidget(self._combo, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    @property
    def current_key(self) -> str:
        return str(self._combo.currentData())


class _ColumnHeaderBar(QWidget):
    """Draggable header bar for configuring CLI columns.

    Uses QSplitter so each cell is resizable by dragging the divider.
    Pixel sizes are converted to percentages on save.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(72)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 4, 0)
        outer.setSpacing(4)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(5)
        self._splitter.setStyleSheet(
            "QSplitter::handle { background: #44446a; border-radius: 2px; }"
        )
        self._splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._splitter.setFixedHeight(72)
        outer.addWidget(self._splitter, 1)

        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setToolTip("Add column")
        add_btn.clicked.connect(self._on_add)
        outer.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self._cells: list[_ColumnCell] = []

    # ---------------------------------------------------------------- public

    def load_columns(self, columns: list) -> None:
        """Populate from a list of NavColumn."""
        for cell in self._cells:
            cell.setParent(None)
            cell.deleteLater()
        self._cells = []
        for col in columns:
            self._append_cell(col.key)
        # Set initial proportional sizes
        total_pct = sum(c.width_pct for c in columns) or 100
        base = 600
        sizes = [max(40, int(c.width_pct * base / total_pct)) for c in columns]
        self._splitter.setSizes(sizes)

    def current_columns(self) -> list:
        """Return list of NavColumn with percentages derived from splitter sizes."""
        from ...core.cli_nav_settings import NavColumn
        sizes = self._splitter.sizes()
        total = sum(sizes) or 1
        result = []
        for cell, px in zip(self._cells, sizes):
            pct = max(1, round(px * 100 / total))
            result.append(NavColumn(key=cell.current_key, width_pct=pct))
        return result if result else [NavColumn("command", 100)]

    # --------------------------------------------------------------- private

    def _append_cell(self, key: str) -> None:
        cell = _ColumnCell(key, self)
        cell.delete_requested.connect(self._on_delete)
        self._cells.append(cell)
        self._splitter.addWidget(cell)

    def _on_add(self) -> None:
        self._append_cell("name")
        # Give new column an equal share
        n = len(self._cells)
        if n > 0:
            equal = 600 // n
            self._splitter.setSizes([equal] * n)

    def _on_delete(self, cell: _ColumnCell) -> None:
        if len(self._cells) <= 1:
            return
        idx = self._cells.index(cell)
        self._cells.pop(idx)
        cell.setParent(None)
        cell.deleteLater()


# ---------------------------------------------------------------------------


class CliOptionsWidget(QWidget):
    def __init__(
        self,
        initial_settings: "CliNavSettings",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color_combos: dict[str, QComboBox] = {}
        self._limit_spins: dict[str, QSpinBox] = {}
        self._col_bar: _ColumnHeaderBar | None = None
        self._wrap_check: QCheckBox | None = None
        self._key_edits: dict[str, tuple["QLineEdit", "QLineEdit"]] = {}
        self._build_ui()
        self._apply_settings(initial_settings)

    # ------------------------------------------------------------------ build

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._build_columns_group())
        layout.addWidget(self._build_colors_group())
        layout.addWidget(self._build_limits_group())
        layout.addWidget(self._build_key_bindings_group())
        reset_btn = QPushButton("Default settings")
        reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(reset_btn)
        layout.addStretch(1)

    def _build_columns_group(self) -> QGroupBox:
        group = QGroupBox("Columns")
        vbox = QVBoxLayout(group)
        vbox.setSpacing(6)

        hint = QLabel(
            "Click a column header to change what it shows.  "
            "Drag the divider between columns to resize."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        vbox.addWidget(hint)

        self._col_bar = _ColumnHeaderBar()
        vbox.addWidget(self._col_bar)

        self._wrap_check = QCheckBox("Wrap text (entries with long content use 2 lines)")
        vbox.addWidget(self._wrap_check)

        return group

    def _build_colors_group(self) -> QGroupBox:
        group = QGroupBox("Section colors")
        grid = QGridLayout(group)
        grid.setSpacing(6)
        for row, (key, label) in enumerate(SECTION_COLOR_LABELS):
            combo = QComboBox()
            for val, display in COLOR_CHOICES:
                combo.addItem(display, userData=val)
            self._color_combos[key] = combo
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(combo, row, 1)
        return group

    def _build_limits_group(self) -> QGroupBox:
        group = QGroupBox("Minimum rows per section")
        grid = QGridLayout(group)
        grid.setSpacing(6)
        for row, (key, label) in enumerate([
            ("heuristic_min", "Heuristic min"),
            ("ai_max", "AI max"),
            ("workflow_min", "Workflow min"),
        ]):
            spin = QSpinBox()
            spin.setRange(0, 20)
            spin.setSuffix(" rows")
            self._limit_spins[key] = spin
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(spin, row, 1)
        return group

    def _build_key_bindings_group(self) -> "QGroupBox":
        from PyQt6.QtWidgets import QGroupBox, QGridLayout, QLabel, QLineEdit
        from ...core.cli_nav_settings import NAV_KEY_BINDING_DEFAULTS, NAV_KEY_BINDING_LABELS
        group = QGroupBox("Key Bindings")
        grid = QGridLayout(group)
        grid.setSpacing(6)
        grid.addWidget(QLabel("Action"), 0, 0)
        grid.addWidget(QLabel("Primary"), 0, 1)
        grid.addWidget(QLabel("Secondary"), 0, 2)
        self._key_edits = {}
        for row, (action, default) in enumerate(NAV_KEY_BINDING_DEFAULTS.items(), start=1):
            grid.addWidget(QLabel(NAV_KEY_BINDING_LABELS[action]), row, 0)
            primary_edit = QLineEdit()
            secondary_edit = QLineEdit()
            primary_edit.setPlaceholderText(default[0])
            primary_edit.setMaximumWidth(100)
            secondary_edit.setMaximumWidth(100)
            grid.addWidget(primary_edit, row, 1)
            grid.addWidget(secondary_edit, row, 2)
            self._key_edits[action] = (primary_edit, secondary_edit)
        hint = QLabel("Key names: Up, Down, Left, Right, Tab, Shift+Tab, Alt+s, or single chars (j, k, q ...)")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888; font-size: 11px;")
        grid.addWidget(hint, len(NAV_KEY_BINDING_DEFAULTS) + 1, 0, 1, 3)
        return group

    # ------------------------------------------------------------------ reset

    def _on_reset(self) -> None:
        from ...core.cli_nav_settings import DEFAULT_CLI_NAV_SETTINGS
        self._apply_settings(DEFAULT_CLI_NAV_SETTINGS)

    # ---------------------------------------------------------- apply/collect

    def _apply_settings(self, s: "CliNavSettings") -> None:
        if self._col_bar is not None:
            self._col_bar.load_columns(s.columns)

        if self._wrap_check is not None:
            self._wrap_check.setChecked(s.wrap_text)

        color_vals = {
            "input": s.colors.input,
            "workflow": s.colors.workflow,
            "heuristic": s.colors.heuristic,
            "ai": s.colors.ai,
        }
        for key, combo in self._color_combos.items():
            val = color_vals.get(key, "default")
            for i in range(combo.count()):
                if combo.itemData(i) == val:
                    combo.setCurrentIndex(i)
                    break

        limit_vals = {
            "heuristic_min": s.section_limits.heuristic_min,
            "ai_max": s.section_limits.ai_max,
            "workflow_min": s.section_limits.workflow_min,
        }
        for key, spin in self._limit_spins.items():
            spin.setValue(limit_vals.get(key, 3))

        kb = s.key_bindings
        kb_vals = {
            "nav_up": kb.nav_up,
            "nav_down": kb.nav_down,
            "nav_left": kb.nav_left,
            "nav_right": kb.nav_right,
            "tab_fill": kb.tab_fill,
            "accept_ghost": kb.accept_ghost,
            "save_new": kb.save_new,
            "quit_nav": kb.quit_nav,
        }
        for action, (primary_edit, secondary_edit) in self._key_edits.items():
            vals = kb_vals.get(action, ["", ""])
            primary_edit.setText(vals[0])
            secondary_edit.setText(vals[1] if len(vals) > 1 else "")

    def current_settings(self) -> "CliNavSettings":
        from ...core.cli_nav_settings import (
            CliNavSettings,
            NavColors,
            NavSectionLimits,
            _default_columns,
        )
        columns = self._col_bar.current_columns() if self._col_bar else _default_columns()
        wrap_text = self._wrap_check.isChecked() if self._wrap_check else False
        colors = NavColors(
            input=str(self._color_combos["input"].currentData()),
            workflow=str(self._color_combos["workflow"].currentData()),
            heuristic=str(self._color_combos["heuristic"].currentData()),
            ai=str(self._color_combos["ai"].currentData()),
        )
        limits = NavSectionLimits(
            heuristic_min=self._limit_spins["heuristic_min"].value(),
            ai_max=self._limit_spins["ai_max"].value(),
            workflow_min=self._limit_spins["workflow_min"].value(),
        )
        from ...core.cli_nav_settings import NavKeyBindings
        key_bindings_raw = {
            action: [primary.text().strip(), secondary.text().strip()]
            for action, (primary, secondary) in self._key_edits.items()
        }
        # Fall back to defaults for empty primary keys
        from ...core.cli_nav_settings import NAV_KEY_BINDING_DEFAULTS
        key_bindings = NavKeyBindings(
            nav_up=key_bindings_raw.get("nav_up") or NAV_KEY_BINDING_DEFAULTS["nav_up"],
            nav_down=key_bindings_raw.get("nav_down") or NAV_KEY_BINDING_DEFAULTS["nav_down"],
            nav_left=key_bindings_raw.get("nav_left") or NAV_KEY_BINDING_DEFAULTS["nav_left"],
            nav_right=key_bindings_raw.get("nav_right") or NAV_KEY_BINDING_DEFAULTS["nav_right"],
            tab_fill=key_bindings_raw.get("tab_fill") or NAV_KEY_BINDING_DEFAULTS["tab_fill"],
            accept_ghost=key_bindings_raw.get("accept_ghost") or NAV_KEY_BINDING_DEFAULTS["accept_ghost"],
            save_new=key_bindings_raw.get("save_new") or NAV_KEY_BINDING_DEFAULTS["save_new"],
            quit_nav=key_bindings_raw.get("quit_nav") or NAV_KEY_BINDING_DEFAULTS["quit_nav"],
        )
        return CliNavSettings(
            columns=columns, colors=colors, section_limits=limits, wrap_text=wrap_text,
            key_bindings=key_bindings,
        )
