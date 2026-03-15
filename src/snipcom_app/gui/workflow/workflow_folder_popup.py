from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QColor, QCursor
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QMessageBox,
)

from ...core.helpers import available_path
from ...core.repository import SnipcomEntry
from ..widgets import FlowLayout, PopupFolderTile

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster


def open_folder(window: "NoteCopyPaster") -> None:
    window._open_workspace_path(window.repository.texts_dir, failure_title="Open folder failed")


def open_folder_entry(
    window: "NoteCopyPaster",
    target: SnipcomEntry | Path | str,
    *,
    force_edit: bool = False,
) -> None:
    entry = window.entry_for(target)
    if entry is None or not entry.is_folder or entry.path is None:
        return
    if force_edit:
        if window._open_workspace_path(entry.path, failure_title="Open folder failed"):
            window.show_status(f"Opened {entry.display_name}.")
        return
    close_active_folder_popup(window)
    show_popup_folder_contents(window, entry)


def close_active_folder_popup(window: "NoteCopyPaster") -> None:
    popup = getattr(window, "active_folder_popup", None)
    if popup is None:
        return
    popup.close()
    window.active_folder_popup = None


def show_popup_folder_contents(
    window: "NoteCopyPaster",
    folder_entry: SnipcomEntry,
    *,
    edit_mode: bool = False,
) -> None:
    if not folder_entry.is_folder or folder_entry.path is None:
        return
    folder_path = folder_entry.path
    try:
        child_entries = window.repository.folder_entries(folder_path, window.tags, window.snip_types)
    except OSError as exc:
        QMessageBox.critical(window, "Open folder failed", str(exc))
        return

    popup_menu = QMenu(window)
    popup_menu.setObjectName("folder-popup-menu")
    popup_menu.setStyleSheet(
        "#folder-popup-menu {"
        "background: rgba(18, 22, 26, 246);"
        "border: 1px solid rgba(255, 255, 255, 40);"
        "padding: 6px;"
        "}"
    )
    window.active_folder_popup = popup_menu
    popup_menu.aboutToHide.connect(lambda: setattr(window, "active_folder_popup", None))

    panel = QWidget(popup_menu)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    info_text = "Double click a file for launch/send actions, or right click any item for full options."
    if not child_entries:
        info_text = (
            "Click the button then select what items to add inside the folder. "
            'You can also activate this function by right clicking the folder and selecting the "Add items to folder".'
        )
    if edit_mode:
        info_text = "Select items inside this folder to move them out or send them to trash."
    info = QLabel(info_text)
    info.setWordWrap(True)
    layout.addWidget(info)

    selection_list = None
    if edit_mode:
        selection_list = QListWidget()
        for entry in child_entries:
            kind = "Folder" if entry.is_folder else ("Command" if entry.is_command else "File")
            item = QListWidgetItem(f"[{kind}] {entry.display_name}")
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            selection_list.addItem(item)
        if selection_list.count():
            layout.addWidget(selection_list, 1)
        else:
            empty_label = QLabel("Empty Folder")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet(
                "color: rgba(224, 230, 236, 0.82);"
                "border: 1px dashed rgba(255, 255, 255, 36);"
                "border-radius: 10px;"
                "padding: 28px 18px;"
            )
            layout.addWidget(empty_label)
            panel.resize(window.scaled_size(360), window.scaled_size(220))
            panel.setMinimumSize(window.scaled_size(360), window.scaled_size(220))
    elif child_entries:
        grid_container = QWidget()
        grid_layout = FlowLayout(grid_container, spacing=window.scaled_size(8))
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_container.setLayout(grid_layout)
        for entry in child_entries:
            grid_layout.addWidget(build_popup_folder_tile(window, entry, popup_menu))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(grid_container)
        layout.addWidget(scroll, 1)

        columns = min(3, max(1, len(child_entries)))
        rows = (len(child_entries) + columns - 1) // columns
        tile_width = window.scaled_size(150)
        tile_height = window.scaled_size(116)
        width = window.scaled_size(56) + columns * tile_width
        height = window.scaled_size(132) + min(rows, 3) * tile_height
        panel.resize(width, height)
        panel.setMinimumSize(width, min(height, window.scaled_size(520)))
    else:
        empty_label = QLabel("Empty Folder")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet(
            "color: rgba(224, 230, 236, 0.82);"
            "border: 1px dashed rgba(255, 255, 255, 36);"
            "border-radius: 10px;"
            "padding: 28px 18px;"
        )
        layout.addWidget(empty_label)
        add_to_folder_button = configure_popup_folder_button(window, "Add items to folder...")
        add_to_folder_button.clicked.connect(lambda: window.begin_add_to_folder_mode(folder_entry))
        layout.addWidget(add_to_folder_button)
        panel.resize(window.scaled_size(360), window.scaled_size(220))
        panel.setMinimumSize(window.scaled_size(360), window.scaled_size(220))

    actions = QWidget()
    actions_layout = QVBoxLayout(actions)
    actions_layout.setContentsMargins(0, 0, 0, 0)
    actions_layout.setSpacing(4)
    if edit_mode:
        action_label = QLabel("What to do with selected items?")
        action_label.setWordWrap(True)
        actions_layout.addWidget(action_label)
        move_out_button = configure_popup_folder_button(window, "Move Out Of Folder")
        delete_button = configure_popup_folder_button(window, "Delete")
        cancel_button = configure_popup_folder_button(window, "Cancel")
        move_out_button.clicked.connect(
            lambda: apply_folder_edit_selection(
                window,
                folder_entry,
                selection_list,
                action="move_out",
                popup_menu=popup_menu,
            )
        )
        delete_button.clicked.connect(
            lambda: apply_folder_edit_selection(
                window,
                folder_entry,
                selection_list,
                action="trash",
                popup_menu=popup_menu,
            )
        )
        cancel_button.clicked.connect(lambda: (popup_menu.close(), show_popup_folder_contents(window, folder_entry)))
        actions_layout.addWidget(move_out_button)
        actions_layout.addWidget(delete_button)
        actions_layout.addWidget(cancel_button)
    else:
        add_items_button = configure_popup_folder_button(window, "Add items to folder...")
        edit_contents_button = configure_popup_folder_button(window, "Edit Folder Contents")
        open_in_explorer_button = configure_popup_folder_button(window, "Open Folder In Explorer")
        close_button = configure_popup_folder_button(window, "Close")
        add_items_button.clicked.connect(lambda: window.begin_add_to_folder_mode(folder_entry))
        edit_contents_button.clicked.connect(lambda: (popup_menu.close(), show_popup_folder_contents(window, folder_entry, edit_mode=True)))
        open_in_explorer_button.clicked.connect(lambda: open_popup_folder_in_explorer(window, folder_entry))
        close_button.clicked.connect(popup_menu.close)
        actions_layout.addWidget(add_items_button)
        actions_layout.addWidget(edit_contents_button)
        actions_layout.addWidget(open_in_explorer_button)
        actions_layout.addWidget(close_button)
    layout.addWidget(actions)

    widget_action = QWidgetAction(popup_menu)
    widget_action.setDefaultWidget(panel)
    popup_menu.addAction(widget_action)

    popup_menu.popup(QCursor.pos())


def configure_popup_folder_button(window: "NoteCopyPaster", text: str) -> QPushButton:
    button = QPushButton(text)
    window.style_action_button(button, compact=True)
    return button


def apply_folder_edit_selection(
    window: "NoteCopyPaster",
    folder_entry: SnipcomEntry,
    selection_list: QListWidget | None,
    *,
    action: str,
    popup_menu: QMenu,
) -> None:
    if selection_list is None or folder_entry.path is None:
        return
    selected_entries: list[SnipcomEntry] = []
    for index in range(selection_list.count()):
        item = selection_list.item(index)
        if item.checkState() != Qt.CheckState.Checked:
            continue
        entry = window.entry_for(str(item.data(Qt.ItemDataRole.UserRole)))
        if entry is not None:
            selected_entries.append(entry)
    if not selected_entries:
        return
    try:
        if action == "move_out":
            for entry in selected_entries:
                if entry.is_file and entry.path is not None:
                    destination = available_path(window.repository.texts_dir, entry.path.name)
                    entry.path.rename(destination)
                    window.repository.move_metadata(window.tags, window.snip_types, window.launch_options, entry.path, destination)
                elif entry.is_command and entry.command_id is not None:
                    window.repository.set_command_folder(entry.command_id, None)
                elif entry.is_folder and entry.path is not None:
                    destination = available_path(window.repository.texts_dir, entry.path.name)
                    entry.path.rename(destination)
                    window.repository.move_metadata(window.tags, window.snip_types, window.launch_options, entry.path, destination)
                    window.repository.reassign_command_folder_prefix(entry.path, destination)
        elif action == "trash":
            for entry in selected_entries:
                if entry.is_file and entry.path is not None:
                    window.move_paths_to_trash([entry.path])
                elif entry.is_command and entry.command_id is not None:
                    window.repository.command_store.move_command_to_trash(entry.command_id)
                elif entry.is_folder and entry.path is not None:
                    window.move_paths_to_trash([entry.path])
                    window.repository.reassign_command_folder_prefix(entry.path, None)
        window.save_tags()
        window.save_snip_types()
        window.save_launch_options()
    except OSError as exc:
        QMessageBox.critical(window, "Folder update failed", str(exc))
        return
    popup_menu.close()
    window.refresh_workflow_views(refresh_search=False)
    show_popup_folder_contents(window, folder_entry)


def build_popup_folder_tile(window: "NoteCopyPaster", entry: SnipcomEntry, popup_menu: QMenu) -> QWidget:
    tile = PopupFolderTile(window, entry)
    tile.popup_menu = popup_menu
    return tile


def open_popup_folder_tile_actions(window: "NoteCopyPaster", entry: SnipcomEntry, anchor: QWidget) -> None:
    popup_menu = getattr(anchor, "popup_menu", None)
    if entry.is_folder:
        if popup_menu is not None:
            popup_menu.close()
        open_folder_entry(window, entry)
        return
    action_menu = QMenu(anchor)
    launch_action = window.configure_menu_action(QAction("Launch", action_menu), "Launch this entry as a command.")
    launch_action.triggered.connect(
        lambda _checked=False: ((popup_menu.close() if popup_menu is not None else None), window.launch_file_content(entry))
    )
    action_menu.addAction(launch_action)
    send_action = window.configure_menu_action(
        QAction("Send Command", action_menu),
        "Send this entry to a linked terminal or choose where to send it.",
    )
    send_action.triggered.connect(
        lambda _checked=False: ((popup_menu.close() if popup_menu is not None else None), window.handle_send_command_button(entry, anchor))
    )
    action_menu.addAction(send_action)
    open_action = window.configure_menu_action(
        QAction("Open", action_menu),
        "Open this entry in the configured editor.",
    )
    open_action.triggered.connect(
        lambda _checked=False: ((popup_menu.close() if popup_menu is not None else None), window.open_file(entry))
    )
    action_menu.addAction(open_action)
    more_menu = window.build_more_menu(entry, action_menu, include_open_action=False, include_paste_actions=True)
    more_menu.menuAction().setText("More options")
    action_menu.addMenu(more_menu)
    action_menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))


def show_popup_folder_tile_context_menu(
    window: "NoteCopyPaster",
    entry: SnipcomEntry,
    anchor: QWidget,
    global_pos: QPoint,
) -> None:
    menu = window.build_more_menu(
        entry,
        anchor,
        include_open_action=not entry.is_folder,
        include_paste_actions=not entry.is_folder,
    )
    menu.exec(global_pos)
    popup_menu = getattr(anchor, "popup_menu", None)
    if popup_menu is not None:
        popup_menu.close()


def open_popup_folder_in_explorer(window: "NoteCopyPaster", folder_entry: SnipcomEntry) -> None:
    close_active_folder_popup(window)
    open_folder_entry(window, folder_entry, force_edit=True)
