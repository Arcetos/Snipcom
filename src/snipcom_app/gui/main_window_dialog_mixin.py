from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QRadioButton,
)
from ..core.snip_types import SNIP_TYPE_HINTS, SNIP_TYPE_LABELS, SNIP_TYPE_ORDER

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowDialogMixin:
    def confirm_risky_command(
        self: "NoteCopyPaster",
        *,
        action_label: str,
        entry_label: str,
        command_text: str,
        reasons: list[str] | tuple[str, ...],
    ) -> bool:
        if not reasons:
            return True
        details = "\n".join(f"- {reason}" for reason in reasons)
        message = QMessageBox(self)
        message.setWindowTitle(f"Confirm {action_label.title()}")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText(f"{entry_label} looks risky for {action_label}.")
        message.setInformativeText("Review the command and reasons before continuing.")
        message.setDetailedText(f"Command:\n{command_text}\n\nReasons:\n{details}")
        proceed_button = message.addButton(f"Proceed with {action_label.title()}", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = message.addButton(QMessageBox.StandardButton.Cancel)
        message.setDefaultButton(cancel_button)
        message.exec()
        return message.clickedButton() == proceed_button

    def prompt_new_file(self: "NoteCopyPaster", default_name: str) -> tuple[str | None, bool, str]:
        dialog = QDialog(self)
        dialog.setWindowTitle("New file")
        dialog.resize(460, 300)
        dialog.setMinimumWidth(420)
        dialog.setMinimumHeight(240)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(6)

        name_label = QLabel("File name:")
        line_edit = QLineEdit(default_name)
        layout.addWidget(name_label)
        layout.addWidget(line_edit)

        content_label = QLabel("Initial content (optional):")
        from PyQt6.QtWidgets import QPlainTextEdit
        content_edit = QPlainTextEdit()
        content_edit.setPlaceholderText("Type something here… press Enter for new lines.")
        content_edit.setMinimumHeight(100)
        layout.addWidget(content_label)
        layout.addWidget(content_edit, 1)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        create_button = QPushButton("Create")
        create_and_open_button = QPushButton("Create and open with editor")
        cancel_button = QPushButton("Cancel")
        buttons_layout.addWidget(create_button)
        buttons_layout.addWidget(create_and_open_button)
        buttons_layout.addWidget(cancel_button)
        layout.addLayout(buttons_layout)

        create_button.clicked.connect(lambda: dialog.done(2))
        create_and_open_button.clicked.connect(lambda: dialog.done(3))
        cancel_button.clicked.connect(dialog.reject)
        create_button.setDefault(True)
        line_edit.selectAll()
        line_edit.setFocus()

        result = dialog.exec()
        if result not in {2, 3}:
            return None, False, ""
        return line_edit.text(), result == 3, content_edit.toPlainText()

    def prompt_new_folder(self: "NoteCopyPaster", default_name: str) -> tuple[str | None, str]:
        dialog = QDialog(self)
        dialog.setWindowTitle("New folder")
        dialog.resize(420, 140)
        dialog.setMinimumWidth(420)

        layout = QVBoxLayout(dialog)
        name_label = QLabel("Folder name:")
        name_input = QLineEdit(default_name)
        layout.addWidget(name_label)
        layout.addWidget(name_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        name_input.selectAll()
        name_input.setFocus()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None, "popup"
        return name_input.text(), "popup"

    def prompt_snip_type(self: "NoteCopyPaster", current_snip_type: str = "text_file") -> str | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose snipType")
        dialog.resize(420, 240)

        layout = QVBoxLayout(dialog)
        help_label = QLabel("Choose the snipType for this new or existing file.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        type_list = QListWidget()
        for snip_type in SNIP_TYPE_ORDER:
            item = QListWidgetItem(f"{SNIP_TYPE_LABELS[snip_type]} | {SNIP_TYPE_HINTS[snip_type]}")
            item.setData(Qt.ItemDataRole.UserRole, snip_type)
            type_list.addItem(item)
            if snip_type == current_snip_type:
                type_list.setCurrentItem(item)
        if type_list.currentRow() < 0:
            type_list.setCurrentRow(0)
        layout.addWidget(type_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        type_list.itemActivated.connect(lambda _item: dialog.accept())
        type_list.setFocus()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        current_item = type_list.currentItem()
        if current_item is None:
            return None
        return str(current_item.data(Qt.ItemDataRole.UserRole))

    def prompt_command_attributes(
        self: "NoteCopyPaster",
        snip_type: str,
        *,
        current_family_key: str = "",
        dangerous: bool = False,
        window_title: str = "Command Details",
    ) -> tuple[str, bool] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(window_title)
        dialog.resize(420, 180)

        layout = QVBoxLayout(dialog)
        help_label = QLabel("Choose command-specific details for this entry.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        family_input: QLineEdit | None = None
        if snip_type == "family_command":
            family_label = QLabel("Family key:")
            family_input = QLineEdit(current_family_key)
            family_input.setPlaceholderText("git, packages, files, crash, ...")
            layout.addWidget(family_label)
            layout.addWidget(family_input)

        dangerous_checkbox = QCheckBox("Mark as dangerous")
        dangerous_checkbox.setChecked(dangerous)
        dangerous_checkbox.setToolTip("Use for destructive or system-changing commands.")
        layout.addWidget(dangerous_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if family_input is not None:
            family_input.setFocus()
            family_input.selectAll()
        else:
            dangerous_checkbox.setFocus()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        family_key = family_input.text().strip() if family_input is not None else ""
        return family_key, dangerous_checkbox.isChecked()

    def prompt_new_user_command(self: "NoteCopyPaster") -> tuple[str, str, str] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("New Command")
        dialog.resize(480, 320)

        layout = QVBoxLayout(dialog)

        title_label = QLabel("Title:")
        title_input = QLineEdit()
        title_input.setPlaceholderText("Command title")
        layout.addWidget(title_label)
        layout.addWidget(title_input)

        body_label = QLabel("Body:")
        body_input = QPlainTextEdit()
        body_input.setPlaceholderText("Command body (the actual command text)")
        body_input.setMinimumHeight(100)
        layout.addWidget(body_label)
        layout.addWidget(body_input)

        desc_label = QLabel("Description (optional):")
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("Brief description")
        layout.addWidget(desc_label)
        layout.addWidget(desc_input)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        title_input.setFocus()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        title = title_input.text().strip()
        if not title:
            return None
        body = body_input.toPlainText()
        description = desc_input.text().strip()
        return title, body, description

    def snip_type_fallback_suffix(self: "NoteCopyPaster", snip_type: str) -> str | None:
        if snip_type == "text_file":
            return ".txt"
        return None
