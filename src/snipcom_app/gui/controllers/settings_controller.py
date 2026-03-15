from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Mapping

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QKeySequence
import shutil

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QKeySequenceEdit,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...ai.ai import AIProviderError, DEFAULT_OLLAMA_ENDPOINT, check_ollama_status
from ...core.helpers import FAVORITES_TAG
from ...integration.linked_terminal import (
    linked_terminal_root_dir,
    refresh_interactive_linked_terminal_bindings,
)

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


class SettingsController:
    def __init__(
        self,
        window: "NoteCopyPaster",
        *,
        quick_search_binding_defaults: Mapping[str, list[str]],
        quick_search_binding_labels: Mapping[str, str],
        terminal_suggestion_binding_defaults: Mapping[str, list[str]],
        terminal_suggestion_binding_labels: Mapping[str, str],
        move_handle_icon: Callable[[int], QIcon],
    ) -> None:
        self.window = window
        self.quick_search_binding_defaults = dict(quick_search_binding_defaults)
        self.quick_search_binding_labels = dict(quick_search_binding_labels)
        self.terminal_suggestion_binding_defaults = dict(terminal_suggestion_binding_defaults)
        self.terminal_suggestion_binding_labels = dict(terminal_suggestion_binding_labels)
        self.move_handle_icon = move_handle_icon

    def _known_tag_colors(self) -> tuple[dict[str, str], list[str]]:
        window = self.window
        tag_color_values = dict(window.tag_color_overrides())
        known_tags = sorted(
            {
                FAVORITES_TAG,
                *tag_color_values.keys(),
                *(tag for entry in window.active_entries() for tag in window.tags_for(entry)),
            },
            key=str.casefold,
        )
        return tag_color_values, known_tags

    def _tag_color_swatch_style(self, color: QColor) -> str:
        return (
            "QLabel {"
            "border: 1px solid rgba(255,255,255,0.24);"
            "border-radius: 6px;"
            f"background-color: {color.name(QColor.NameFormat.HexRgb)};"
            "color: rgba(12, 16, 20, 0.92);"
            "padding: 2px 8px;"
            "font-weight: 600;"
            "}"
        )

    def _tag_color_empty_swatch_style(self) -> str:
        return (
            "QLabel {"
            "border: 1px dashed rgba(255,255,255,0.26);"
            "border-radius: 6px;"
            "background-color: rgba(255,255,255,0.04);"
            "color: rgba(216,222,228,0.80);"
            "padding: 2px 8px;"
            "}"
        )

    def _refresh_tag_color_swatch(self, swatch: QLabel, tag_key: str, tag_color_values: dict[str, str]) -> None:
        window = self.window
        color_text = str(tag_color_values.get(tag_key, "")).strip()
        color = QColor(color_text)
        if not color.isValid() and tag_key == FAVORITES_TAG:
            color = QColor(window.tag_color_for_tag(FAVORITES_TAG))
        if color.isValid():
            swatch.setText(color.name(QColor.NameFormat.HexRgb))
            swatch.setStyleSheet(self._tag_color_swatch_style(color))
            return
        swatch.setText("default")
        swatch.setStyleSheet(self._tag_color_empty_swatch_style())

    def _build_tag_color_row(
        self,
        dialog: QDialog,
        tag: str,
        tag_color_values: dict[str, str],
    ) -> QWidget:
        window = self.window
        tag_key = tag.casefold()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        tag_label = QLabel(tag)
        tag_label.setMinimumWidth(140)
        color_swatch = QLabel()
        color_swatch.setMinimumWidth(84)
        color_swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)

        choose_button = QPushButton("Set Color")
        clear_button = QPushButton("Clear")

        def refresh() -> None:
            self._refresh_tag_color_swatch(color_swatch, tag_key, tag_color_values)

        def choose_color(_checked: bool = False) -> None:
            current = QColor(str(tag_color_values.get(tag_key, "")).strip())
            if not current.isValid():
                current = QColor(window.tag_color_for_tag(tag))
            picked = QColorDialog.getColor(current, dialog, f"Choose color for tag: {tag}")
            if not picked.isValid():
                return
            tag_color_values[tag_key] = picked.name(QColor.NameFormat.HexRgb)
            refresh()

        def clear_color(_checked: bool = False) -> None:
            tag_color_values.pop(tag_key, None)
            refresh()

        choose_button.clicked.connect(choose_color)
        clear_button.clicked.connect(clear_color)
        refresh()

        row_layout.addWidget(tag_label)
        row_layout.addWidget(color_swatch)
        row_layout.addWidget(choose_button)
        row_layout.addWidget(clear_button)
        row_layout.addStretch(1)
        return row

    def _cleaned_tag_color_settings(self, tag_color_values: dict[str, str]) -> dict[str, str]:
        cleaned_tag_colors: dict[str, str] = {}
        for tag_key, color_value in tag_color_values.items():
            color = QColor(str(color_value).strip())
            if not color.isValid():
                continue
            cleaned_tag_colors[str(tag_key).strip().casefold()] = color.name(QColor.NameFormat.HexRgb)
        return cleaned_tag_colors

    def show_options_dialog(self) -> None:
        window = self.window
        dialog = QDialog(window)
        dialog.setWindowTitle("Options")
        dialog.resize(620, 480)

        layout = QVBoxLayout(dialog)
        tabs = QTabWidget(dialog)
        layout.addWidget(tabs)

        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(10)

        texts_group = QGroupBox("Texts Folder")
        texts_layout = QVBoxLayout()
        texts_label = QLabel(str(window.repository.texts_dir))
        texts_label.setWordWrap(True)
        texts_buttons = QHBoxLayout()
        choose_texts_button = QPushButton("Choose...")
        default_texts_button = QPushButton("Use Default")
        texts_buttons.addWidget(choose_texts_button)
        texts_buttons.addWidget(default_texts_button)
        texts_buttons.addStretch(1)
        texts_layout.addWidget(texts_label)
        texts_layout.addLayout(texts_buttons)
        texts_group.setLayout(texts_layout)
        general_layout.addWidget(texts_group)

        terminal_group = QGroupBox("Terminal Launcher")
        terminal_layout = QVBoxLayout()
        terminal_label = QLabel(window.current_terminal_label())
        terminal_label.setWordWrap(True)
        terminal_buttons = QHBoxLayout()
        choose_terminal_button = QPushButton("Choose...")
        auto_terminal_button = QPushButton("Use Auto Detect")
        terminal_buttons.addWidget(choose_terminal_button)
        terminal_buttons.addWidget(auto_terminal_button)
        terminal_buttons.addStretch(1)
        terminal_layout.addWidget(terminal_label)
        terminal_layout.addLayout(terminal_buttons)
        terminal_group.setLayout(terminal_layout)
        general_layout.addWidget(terminal_group)

        explorer_group = QGroupBox("Explorer")
        explorer_layout = QVBoxLayout()
        explorer_label = QLabel(window.current_folder_opener_label())
        explorer_label.setWordWrap(True)
        explorer_buttons = QHBoxLayout()
        choose_explorer_button = QPushButton("Choose...")
        auto_explorer_button = QPushButton("Use Auto Detect")
        explorer_buttons.addWidget(choose_explorer_button)
        explorer_buttons.addWidget(auto_explorer_button)
        explorer_buttons.addStretch(1)
        explorer_layout.addWidget(explorer_label)
        explorer_layout.addLayout(explorer_buttons)
        explorer_group.setLayout(explorer_layout)
        general_layout.addWidget(explorer_group)

        window_group = QGroupBox("Window")
        window_layout = QVBoxLayout()
        window_bar_checkbox = QCheckBox("Remove window bar")
        window_bar_checkbox.setChecked(window.window_bar_removed)
        window_help = QLabel(
            "Without the window bar, the app looks more like a widget. "
            "While enabled, resize from the window corners and move it by holding the move button. "
            "You can still close it from Settings > Quit."
        )
        window_help.setWordWrap(True)
        window_help.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        move_preview_row = QHBoxLayout()
        move_preview_row.setContentsMargins(0, 0, 0, 0)
        move_preview_icon = QLabel()
        move_preview_icon.setPixmap(self.move_handle_icon(18).pixmap(18, 18))
        move_preview_icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        move_preview_label = QLabel("Move button shown in the top bar when the window bar is removed.")
        move_preview_label.setWordWrap(True)
        move_preview_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        move_preview_row.addWidget(move_preview_icon)
        move_preview_row.addWidget(move_preview_label, 1)
        window_layout.addWidget(window_bar_checkbox)
        window_layout.addWidget(window_help)
        window_layout.addLayout(move_preview_row)
        window_group.setLayout(window_layout)
        general_layout.addWidget(window_group)
        general_layout.addStretch(1)
        tabs.addTab(general_tab, "General")

        keybindings_tab = QWidget()
        keybindings_layout = QVBoxLayout(keybindings_tab)
        keybindings_layout.setContentsMargins(0, 0, 0, 0)
        keybindings_layout.setSpacing(10)
        quick_search_group = QGroupBox("Quick Search")
        quick_search_layout = QGridLayout()
        quick_search_layout.setContentsMargins(8, 8, 8, 8)
        quick_search_layout.setHorizontalSpacing(10)
        quick_search_layout.setVerticalSpacing(8)
        quick_search_layout.addWidget(QLabel("Action"), 0, 0)
        quick_search_layout.addWidget(QLabel("Primary"), 0, 1)
        quick_search_layout.addWidget(QLabel("Secondary"), 0, 2)
        quick_search_binding_edits: dict[str, tuple[QKeySequenceEdit, QKeySequenceEdit]] = {}
        for row, action in enumerate(self.quick_search_binding_defaults, start=1):
            quick_search_layout.addWidget(QLabel(self.quick_search_binding_labels[action]), row, 0)
            primary_edit = QKeySequenceEdit()
            secondary_edit = QKeySequenceEdit()
            bindings = window.quick_search_bindings.get(action, self.quick_search_binding_defaults[action])
            primary_edit.setKeySequence(QKeySequence(str(bindings[0])))
            secondary_edit.setKeySequence(QKeySequence(str(bindings[1])))
            quick_search_layout.addWidget(primary_edit, row, 1)
            quick_search_layout.addWidget(secondary_edit, row, 2)
            quick_search_binding_edits[action] = (primary_edit, secondary_edit)
        quick_search_group.setLayout(quick_search_layout)
        keybindings_layout.addWidget(quick_search_group)

        terminal_group_bindings = QGroupBox("Linked Terminal Suggestions")
        terminal_binding_layout = QGridLayout()
        terminal_binding_layout.setContentsMargins(8, 8, 8, 8)
        terminal_binding_layout.setHorizontalSpacing(10)
        terminal_binding_layout.setVerticalSpacing(8)
        terminal_binding_layout.addWidget(QLabel("Action"), 0, 0)
        terminal_binding_layout.addWidget(QLabel("Primary"), 0, 1)
        terminal_binding_layout.addWidget(QLabel("Secondary"), 0, 2)
        terminal_binding_edits: dict[str, tuple[QKeySequenceEdit, QKeySequenceEdit]] = {}
        for row, action in enumerate(self.terminal_suggestion_binding_defaults, start=1):
            terminal_binding_layout.addWidget(QLabel(self.terminal_suggestion_binding_labels[action]), row, 0)
            primary_edit = QKeySequenceEdit()
            secondary_edit = QKeySequenceEdit()
            bindings = window.terminal_suggestion_bindings.get(action, self.terminal_suggestion_binding_defaults[action])
            primary_edit.setKeySequence(QKeySequence(str(bindings[0])))
            secondary_edit.setKeySequence(QKeySequence(str(bindings[1])))
            terminal_binding_layout.addWidget(primary_edit, row, 1)
            terminal_binding_layout.addWidget(secondary_edit, row, 2)
            terminal_binding_edits[action] = (primary_edit, secondary_edit)
        terminal_binding_help = QLabel(
            "Linked-terminal suggestion insertion currently works best with Alt-based bindings."
        )
        terminal_binding_help.setWordWrap(True)
        terminal_binding_layout.addWidget(
            terminal_binding_help,
            len(window.terminal_suggestion_bindings or {}) + 1,
            0,
            1,
            3,
        )
        terminal_group_bindings.setLayout(terminal_binding_layout)
        keybindings_layout.addWidget(terminal_group_bindings)

        main_window_group = QGroupBox("Main Window")
        main_window_layout_grid = QGridLayout()
        main_window_layout_grid.setContentsMargins(8, 8, 8, 8)
        main_window_layout_grid.setHorizontalSpacing(10)
        main_window_layout_grid.setVerticalSpacing(8)
        main_window_layout_grid.addWidget(QLabel("Action"), 0, 0)
        main_window_layout_grid.addWidget(QLabel("Primary"), 0, 1)
        main_window_layout_grid.addWidget(QLabel("Secondary"), 0, 2)
        main_window_binding_edits: dict[str, tuple[QKeySequenceEdit, QKeySequenceEdit]] = {}
        mw_binding_labels = window.main_window_binding_labels
        for row, action in enumerate(window.main_window_binding_defaults, start=1):
            main_window_layout_grid.addWidget(QLabel(mw_binding_labels[action]), row, 0)
            primary_edit = QKeySequenceEdit()
            secondary_edit = QKeySequenceEdit()
            bindings = window.main_window_bindings.get(action, window.main_window_binding_defaults[action])
            primary_edit.setKeySequence(QKeySequence(str(bindings[0])))
            secondary_edit.setKeySequence(QKeySequence(str(bindings[1])))
            main_window_layout_grid.addWidget(primary_edit, row, 1)
            main_window_layout_grid.addWidget(secondary_edit, row, 2)
            main_window_binding_edits[action] = (primary_edit, secondary_edit)
        main_window_group.setLayout(main_window_layout_grid)
        keybindings_layout.addWidget(main_window_group)
        keybindings_layout.addStretch(1)
        tabs.addTab(keybindings_tab, "Key Bindings")

        tag_colors_tab = QWidget()
        tag_colors_layout = QVBoxLayout(tag_colors_tab)
        tag_colors_layout.setContentsMargins(0, 0, 0, 0)
        tag_colors_layout.setSpacing(10)
        tag_colors_help = QLabel(
            "Assign a color to each tag. Tagged entries use this color in table and grid views."
        )
        tag_colors_help.setWordWrap(True)
        tag_colors_layout.addWidget(tag_colors_help)

        tag_colors_scroll = QScrollArea()
        tag_colors_scroll.setWidgetResizable(True)
        tag_colors_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tag_colors_content = QWidget()
        tag_colors_content_layout = QVBoxLayout(tag_colors_content)
        tag_colors_content_layout.setContentsMargins(0, 0, 0, 0)
        tag_colors_content_layout.setSpacing(6)
        tag_colors_scroll.setWidget(tag_colors_content)
        tag_colors_layout.addWidget(tag_colors_scroll, 1)
        tabs.addTab(tag_colors_tab, "Tag Colors")

        tag_color_values, known_tags = self._known_tag_colors()
        for tag in known_tags:
            tag_colors_content_layout.addWidget(self._build_tag_color_row(dialog, tag, tag_color_values))

        tag_colors_content_layout.addStretch(1)

        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_layout.setContentsMargins(0, 0, 0, 0)
        ai_layout.setSpacing(10)

        ai_group = QGroupBox("Local AI")
        ai_group_layout = QGridLayout()
        ai_group_layout.setContentsMargins(8, 8, 8, 8)
        ai_group_layout.setHorizontalSpacing(10)
        ai_group_layout.setVerticalSpacing(8)

        ai_enabled_checkbox = QCheckBox("Enable local AI")
        ai_enabled_checkbox.setChecked(window.ai_enabled())
        ai_provider_label = QLabel("Provider")
        ai_provider_value = QLabel("Ollama")
        ai_endpoint_label = QLabel("Endpoint")
        ai_endpoint_input = QLineEdit(window.ai_endpoint())
        ai_model_label = QLabel("Model")
        ai_model_input = QLineEdit(window.ai_model())
        ai_timeout_label = QLabel("Timeout")
        ai_timeout_input = QLineEdit(str(window.ai_timeout_seconds()))
        ai_status_label = QLabel("Local AI is optional and off by default.")
        ai_status_label.setWordWrap(True)
        ai_check_button = QPushButton("Check Connection")

        ai_group_layout.addWidget(ai_enabled_checkbox, 0, 0, 1, 2)
        ai_group_layout.addWidget(ai_provider_label, 1, 0)
        ai_group_layout.addWidget(ai_provider_value, 1, 1)
        ai_group_layout.addWidget(ai_endpoint_label, 2, 0)
        ai_group_layout.addWidget(ai_endpoint_input, 2, 1)
        ai_group_layout.addWidget(ai_model_label, 3, 0)
        ai_group_layout.addWidget(ai_model_input, 3, 1)
        ai_group_layout.addWidget(ai_timeout_label, 4, 0)
        ai_group_layout.addWidget(ai_timeout_input, 4, 1)
        ai_group_layout.addWidget(ai_check_button, 5, 0)
        ai_group_layout.addWidget(ai_status_label, 5, 1)
        ai_group.setLayout(ai_group_layout)
        ai_layout.addWidget(ai_group)

        # Recommended model installer
        install_group = QGroupBox("Install a recommended Ollama model")
        install_group_layout = QVBoxLayout()
        install_group_layout.setContentsMargins(8, 8, 8, 8)
        install_group_layout.setSpacing(6)
        install_note = QLabel("Choose a model to install via <code>ollama pull</code>. GPU requirements are approximate.")
        install_note.setWordWrap(True)
        install_group_layout.addWidget(install_note)

        RECOMMENDED_MODELS = [
            ("qwen2.5:7b", "Qwen 2.5 7B — recommended default, good quality/speed balance. ~5 GB VRAM (GPU) or CPU."),
            ("qwen2.5:3b", "Qwen 2.5 3B — lighter and faster. ~2.5 GB VRAM or CPU. Good for low-end systems."),
            ("llama3.2:3b", "Llama 3.2 3B — Meta's compact model. ~2.5 GB VRAM or CPU. Great general reasoning."),
            ("llama3.1:8b", "Llama 3.1 8B — strong general model. ~6 GB VRAM recommended."),
            ("phi3:mini", "Phi-3 Mini (3.8B) — Microsoft model, very fast on CPU. ~2.5 GB VRAM or CPU."),
            ("mistral:7b", "Mistral 7B — efficient European model, good coding. ~5 GB VRAM recommended."),
            ("deepseek-coder:6.7b", "DeepSeek Coder 6.7B — specialized for code. ~5 GB VRAM recommended."),
        ]

        model_list = QListWidget()
        model_list.setMaximumHeight(140)
        for model_id, model_desc in RECOMMENDED_MODELS:
            item = QListWidgetItem(model_desc)
            item.setData(Qt.ItemDataRole.UserRole, model_id)
            model_list.addItem(item)
        model_list.setCurrentRow(0)
        install_group_layout.addWidget(model_list)

        install_btn = QPushButton("Install selected model (runs ollama pull in a terminal)")
        install_group_layout.addWidget(install_btn)
        install_group.setLayout(install_group_layout)
        ai_layout.addWidget(install_group)
        ai_layout.addStretch(1)
        tabs.addTab(ai_tab, "AI")

        # CLI Options tab
        from ...core.cli_nav_settings import load_cli_nav_settings, dump_cli_nav_settings
        from .cli_options_widget import CliOptionsWidget
        _cli_initial = load_cli_nav_settings(window.settings)
        cli_options_widget = CliOptionsWidget(_cli_initial)
        cli_options_scroll = QScrollArea()
        cli_options_scroll.setWidgetResizable(True)
        cli_options_scroll.setWidget(cli_options_widget)
        tabs.addTab(cli_options_scroll, "CLI Options")

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        def update_labels() -> None:
            texts_label.setText(str(window.repository.texts_dir))
            terminal_label.setText(window.current_terminal_label())
            explorer_label.setText(window.current_folder_opener_label())

        def use_default_texts_folder() -> None:
            window.apply_texts_root_change(window.profile_manager.default_texts_dir())
            update_labels()

        def choose_terminal() -> None:
            window.choose_terminal_executable(dialog)
            update_labels()

        def reset_terminal() -> None:
            window.reset_saved_override("terminal_executable")
            update_labels()
            window.show_toast("Terminal launcher reset to automatic detection.")

        def choose_explorer() -> None:
            window.choose_opener_executable("folder_opener_executable", "Choose explorer application", dialog)
            update_labels()

        def reset_explorer() -> None:
            window.reset_saved_override("folder_opener_executable")
            update_labels()
            window.show_toast("Explorer reset to automatic detection.")

        def check_ai_settings_connection() -> None:
            endpoint = ai_endpoint_input.text().strip() or DEFAULT_OLLAMA_ENDPOINT
            model = ai_model_input.text().strip()
            try:
                timeout_seconds = max(5, int(ai_timeout_input.text().strip() or window.ai_timeout_seconds()))
            except ValueError:
                timeout_seconds = window.ai_timeout_seconds()
            try:
                status = check_ollama_status(endpoint, model, timeout=timeout_seconds)
            except AIProviderError as exc:
                ai_status_label.setText(str(exc))
                return
            ai_status_label.setText(status.message)

        choose_texts_button.clicked.connect(lambda: window.change_texts_folder(dialog) and update_labels())
        default_texts_button.clicked.connect(use_default_texts_folder)
        choose_terminal_button.clicked.connect(choose_terminal)
        auto_terminal_button.clicked.connect(reset_terminal)
        choose_explorer_button.clicked.connect(choose_explorer)
        auto_explorer_button.clicked.connect(reset_explorer)
        ai_check_button.clicked.connect(check_ai_settings_connection)

        def install_selected_model() -> None:
            item = model_list.currentItem()
            if item is None:
                return
            model_id = item.data(Qt.ItemDataRole.UserRole)
            ollama_bin = shutil.which("ollama")
            if not ollama_bin:
                QMessageBox.warning(dialog, "Ollama not found",
                    "Could not find 'ollama' in PATH. Install Ollama first from https://ollama.com.")
                return
            launched = window.launch_in_terminal(
                f"ollama pull {model_id}; echo; echo '--- Done. Press Enter to close ---'; read",
                keep_open=True,
            )
            if not launched:
                QMessageBox.information(dialog, "Manual install",
                    f"Run this command in a terminal:\n\n  ollama pull {model_id}")
                return
            ai_model_input.setText(model_id)
            ai_status_label.setText(f"Started 'ollama pull {model_id}' — see the terminal window for progress.")

        install_btn.clicked.connect(install_selected_model)
        update_labels()

        dialog.exec()
        previous_ai_settings = {
            "enabled": bool(window.settings.get("ai_enabled", False)),
            "provider": str(window.settings.get("ai_provider", "ollama")),
            "endpoint": str(window.settings.get("ai_endpoint", DEFAULT_OLLAMA_ENDPOINT)),
            "model": str(window.settings.get("ai_model", "qwen2.5:7b")),
            "timeout": int(window.settings.get("ai_timeout_seconds", window.ai_timeout_seconds())),
        }

        def read_binding_edits(edits: Mapping[str, tuple[QKeySequenceEdit, QKeySequenceEdit]]) -> dict[str, list[str]]:
            return {
                action: [
                    primary_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText).strip(),
                    secondary_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText).strip(),
                ]
                for action, (primary_edit, secondary_edit) in edits.items()
            }

        window.quick_search_bindings = read_binding_edits(quick_search_binding_edits)
        window.search_controller.clear_quick_search_sequence_state()
        window.save_quick_search_bindings()

        window.terminal_suggestion_bindings = read_binding_edits(terminal_binding_edits)
        window.save_terminal_suggestion_bindings()
        refresh_interactive_linked_terminal_bindings(linked_terminal_root_dir(), window.settings)

        window.main_window_bindings = read_binding_edits(main_window_binding_edits)
        window.save_main_window_bindings()
        for action, shortcut in window.main_window_shortcuts.items():
            seq_str = window.main_window_bindings.get(action, window.main_window_binding_defaults[action])[0]
            shortcut.setKey(QKeySequence(seq_str))

        window.settings["cli_nav"] = dump_cli_nav_settings(cli_options_widget.current_settings())
        window.settings["ai_enabled"] = ai_enabled_checkbox.isChecked()
        window.settings["ai_provider"] = "ollama"
        window.settings["ai_endpoint"] = ai_endpoint_input.text().strip() or DEFAULT_OLLAMA_ENDPOINT
        window.settings["ai_model"] = ai_model_input.text().strip() or "qwen2.5:7b"
        try:
            window.settings["ai_timeout_seconds"] = max(
                5, int(ai_timeout_input.text().strip() or window.ai_timeout_seconds())
            )
        except ValueError:
            window.settings["ai_timeout_seconds"] = window.ai_timeout_seconds()

        current_ai_settings = {
            "enabled": bool(window.settings.get("ai_enabled", False)),
            "provider": str(window.settings.get("ai_provider", "ollama")),
            "endpoint": str(window.settings.get("ai_endpoint", DEFAULT_OLLAMA_ENDPOINT)),
            "model": str(window.settings.get("ai_model", "qwen2.5:7b")),
            "timeout": int(window.settings.get("ai_timeout_seconds", window.ai_timeout_seconds())),
        }
        if current_ai_settings != previous_ai_settings:
            window.clear_search_inline_ai_state()
            window.terminal_controller.clear_terminal_inline_ai_state()

        cleaned_tag_colors = self._cleaned_tag_color_settings(tag_color_values)
        if cleaned_tag_colors:
            window.settings["tag_colors"] = cleaned_tag_colors
        else:
            window.settings.pop("tag_colors", None)

        window.save_settings()
        window.refresh_table()
        self.window.terminal_controller.refresh_linked_terminal_toolbar()
        if window_bar_checkbox.isChecked() != window.window_bar_removed:
            window.apply_window_bar_setting(window_bar_checkbox.isChecked())
            if window.window_bar_removed:
                window.show_feedback("Window bar removed.")
            else:
                window.show_feedback("Window bar restored.")
