from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizeGrip,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .widgets import FlowLayout, RoundedTableItemDelegate

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


def new_search_results_list(window: "NoteCopyPaster") -> QListWidget:
    results = QListWidget()
    results.itemClicked.connect(window.search_controller.focus_search_result)
    results.itemActivated.connect(window.search_controller.open_search_result)
    results.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    results.customContextMenuRequested.connect(
        lambda pos, w=results: window.search_controller.show_search_result_context_menu(w, pos)
    )
    results.installEventFilter(window)
    results.setWordWrap(True)
    results.setTextElideMode(Qt.TextElideMode.ElideNone)
    return results


def new_search_results_group(window: "NoteCopyPaster", title: str, widget: QListWidget) -> QGroupBox:
    group = QGroupBox(title)
    layout = QVBoxLayout()
    layout.addWidget(widget)
    group.setLayout(layout)
    return group


def build_search_results_widget(window: "NoteCopyPaster") -> None:
    window.title_results = new_search_results_list(window)
    window.content_results = new_search_results_list(window)
    window.command_results = new_search_results_list(window)
    window.command_results_secondary = new_search_results_list(window)

    window.title_group = new_search_results_group(window, "Found in title (0)", window.title_results)
    window.content_group = new_search_results_group(window, "Found inside file (0)", window.content_results)
    window.command_group = new_search_results_group(window, "Suggested commands (0)", window.command_results)

    window.search_results_widget = QWidget()
    search_results_layout = QVBoxLayout()
    search_results_layout.setContentsMargins(0, 0, 0, 0)
    search_results_layout.setSpacing(8)
    search_results_layout.addWidget(window.command_group, 3)
    top_search_row = QHBoxLayout()
    top_search_row.setContentsMargins(0, 0, 0, 0)
    top_search_row.setSpacing(8)
    top_search_row.addWidget(window.title_group)
    top_search_row.addWidget(window.content_group)
    search_results_layout.addLayout(top_search_row, 1)
    window.search_results_widget.setLayout(search_results_layout)
    window.search_results_widget.setVisible(False)


def build_top_bar_controls(window: "NoteCopyPaster", main_window_module) -> None:
    window.new_button = QPushButton("New")
    window.new_button.clicked.connect(window.workflow_controller.create_new_file)
    window.new_folder_button = QPushButton("New Folder")
    window.new_folder_button.clicked.connect(window.workflow_controller.create_new_folder)
    window.attach_action_hint(
        window.new_folder_button,
        "Create a new popup folder.",
    )

    window.open_folder_button = QPushButton("Open Folder")
    window.open_folder_button.clicked.connect(window.open_folder)

    window.top_more_button = QToolButton()
    window.top_more_button.setText("Settings")
    window.top_more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.top_more_menu = QMenu(window.top_more_button)
    window.top_more_button.setMenu(window.top_more_menu)
    window.attach_action_hint(window.top_more_button, "Open settings, trash actions, reset, store, and quit.")
    window.populate_top_more_menu()

    window.move_window_handle = QFrame()
    window.move_window_handle.setObjectName("move-window-handle")
    window.move_window_handle.setCursor(Qt.CursorShape.SizeAllCursor)
    window.move_window_handle.setStyleSheet("#move-window-handle { background: transparent; border: none; }")
    move_handle_layout = QHBoxLayout(window.move_window_handle)
    move_handle_layout.setContentsMargins(4, 0, 4, 0)
    move_handle_layout.setSpacing(0)
    move_icon_label = QLabel()
    move_icon_label.setPixmap(main_window_module.move_handle_icon(18).pixmap(18, 18))
    move_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    move_handle_layout.addWidget(move_icon_label)
    window.move_window_handle.installEventFilter(window)
    move_icon_label.installEventFilter(window)
    window.attach_action_hint(
        window.move_window_handle,
        "Hold and drag this handle to move the window when the window bar is removed.",
    )

    window.top_bar_widget = QWidget()
    top_bar = QHBoxLayout(window.top_bar_widget)
    top_bar.setContentsMargins(0, 0, 0, 0)
    top_bar.addWidget(window.new_button)
    top_bar.addWidget(window.new_folder_button)
    top_bar.addWidget(window.open_folder_button)
    top_bar.addWidget(window.undo_button)
    top_bar.addSpacing(12)
    top_bar.addWidget(window.search_input, 1)
    top_bar.addSpacing(12)
    top_bar.addWidget(window.main_family_filter_button)
    top_bar.addWidget(window.profile_button)
    top_bar.addWidget(window.move_window_handle)
    top_bar.addWidget(window.top_more_button)


def build_terminal_toolbar_controls(window: "NoteCopyPaster") -> None:
    window.open_linked_terminal_button = QPushButton("Open Linked Terminal")
    window.open_linked_terminal_button.clicked.connect(window.terminal_controller.open_linked_terminal)
    window.attach_action_hint(
        window.open_linked_terminal_button,
        "Open a linked terminal without queuing an initial command.",
    )

    window.terminal_selector_button = QToolButton()
    window.terminal_selector_button.setText("Terminal Linked")
    window.terminal_selector_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.attach_action_hint(
        window.terminal_selector_button,
        "Choose which linked terminal the bottom bar controls.",
    )

    window.terminal_command_input = QLineEdit()
    window.terminal_command_input.setPlaceholderText("Send a command directly into the selected linked terminal...")
    window.terminal_command_input.returnPressed.connect(window.terminal_controller.send_terminal_input_command)
    window.terminal_command_input.textChanged.connect(window.terminal_controller.handle_terminal_input_text_changed)
    window.terminal_command_input.installEventFilter(window)
    window.attach_action_hint(
        window.terminal_command_input,
        "Type a command and press Enter to send it to the selected linked terminal.",
    )
    window.terminal_send_action = window.terminal_command_input.addAction(
        window.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
        QLineEdit.ActionPosition.LeadingPosition,
    )
    window.terminal_send_action.triggered.connect(window.terminal_controller.send_terminal_input_command)

    window.terminal_ai_suggestion_label = QLabel()
    window.terminal_ai_suggestion_label.setWordWrap(True)
    window.terminal_ai_suggestion_label.hide()
    window.terminal_ai_suggestion_label.setStyleSheet("color: #d6dce5; padding: 0 6px 2px 6px;")

    window.copy_terminal_output_button = QPushButton("Copy Output")
    window.copy_terminal_output_button.clicked.connect(window.terminal_controller.copy_selected_terminal_output)
    window.attach_action_hint(
        window.copy_terminal_output_button,
        "Copy the last captured output from the selected linked terminal.",
    )

    window.save_terminal_output_button = QPushButton("Save Output")
    window.save_terminal_output_button.clicked.connect(window.terminal_controller.save_selected_terminal_output_to_new_file)
    window.attach_action_hint(
        window.save_terminal_output_button,
        "Create a new file and store the selected linked terminal output inside it.",
    )

    window.append_terminal_output_button = QPushButton("Append To File")
    window.append_terminal_output_button.clicked.connect(window.terminal_controller.begin_append_selected_terminal_output)
    window.attach_action_hint(
        window.append_terminal_output_button,
        "Choose an existing file and append the selected linked terminal output into it.",
    )

    window.terminal_toolbar_widget = QWidget()
    terminal_toolbar_layout = QHBoxLayout(window.terminal_toolbar_widget)
    terminal_toolbar_layout.setContentsMargins(0, 0, 0, 0)
    terminal_toolbar_layout.setSpacing(8)
    terminal_input_column = QVBoxLayout()
    terminal_input_column.setContentsMargins(0, 0, 0, 0)
    terminal_input_column.setSpacing(2)
    terminal_input_column.addWidget(window.terminal_command_input)
    terminal_input_column.addWidget(window.terminal_ai_suggestion_label)
    terminal_toolbar_layout.addWidget(window.terminal_selector_button)
    terminal_toolbar_layout.addLayout(terminal_input_column, 1)
    terminal_toolbar_layout.addWidget(window.copy_terminal_output_button)
    terminal_toolbar_layout.addWidget(window.save_terminal_output_button)
    terminal_toolbar_layout.addWidget(window.append_terminal_output_button)
    window.terminal_toolbar_widget.hide()


_COLUMN_LABELS: dict[str, str] = {
    "name": "File name",
    "description": "Description",
    "tag": "Tag",
    "family": "Family",
    "modified": "Modified",
    "actions": "Actions",
}


def build_table_view(window: "NoteCopyPaster") -> None:
    columns = window.table_columns
    window.table = QTableWidget(0, len(columns))
    window.table.setHorizontalHeaderLabels([_COLUMN_LABELS.get(k, k.title()) for k in columns])
    window.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    window.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    window.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.table.setAlternatingRowColors(False)
    window.table.verticalHeader().setVisible(False)
    window.table.verticalHeader().setMinimumSectionSize(46)
    window.table.setItemDelegate(RoundedTableItemDelegate(window))
    header = window.table.horizontalHeader()
    header.setMinimumSectionSize(18)
    for col in range(len(columns)):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
    header.setSectionsMovable(True)
    header.setSortIndicatorShown(True)
    header.sectionClicked.connect(window.view_controller.handle_header_click)
    header.sectionResized.connect(window.handle_column_resized)
    header.sectionMoved.connect(window.handle_column_moved)
    header.geometriesChanged.connect(window.update_tag_header_filter_button)
    header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    header.customContextMenuRequested.connect(window.view_controller.show_header_context_menu)
    window.table.cellDoubleClicked.connect(window.view_controller.handle_cell_double_click)
    window.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    window.table.customContextMenuRequested.connect(window.view_controller.show_table_context_menu)
    window.table.viewport().setMouseTracking(True)
    window.table.viewport().installEventFilter(window)

    window.tag_filter_header_button = QToolButton(header.viewport())
    window.tag_filter_header_button.setAutoRaise(True)
    filter_icon = window.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)
    window.tag_filter_header_button.setIcon(filter_icon)
    window.tag_filter_header_button.clicked.connect(window.filter_controller.show_table_tag_filter_menu)
    window.attach_action_hint(window.tag_filter_header_button, "Filter files by one or more tags.")
    window.tag_filter_header_button.show()
    window.apply_saved_column_order()


def build_grid_view(window: "NoteCopyPaster") -> None:
    window.grid_sort_bar = QWidget()
    window.grid_sort_bar.setObjectName("grid-sort-bar")
    grid_sort_layout = QHBoxLayout(window.grid_sort_bar)
    grid_sort_layout.setContentsMargins(0, 0, 0, 0)
    grid_sort_layout.setSpacing(6)
    for column, label in ((0, "Name"), (1, "Family"), (2, "Tag"), (3, "Modified")):
        button = QPushButton(label)
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, col=column: window.set_sort_column(col))
        window.grid_sort_buttons[column] = button
        grid_sort_layout.addWidget(button)

    window.grid_tag_filter_button = QToolButton()
    window.grid_tag_filter_button.setText("Tag Select")
    window.grid_tag_filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.grid_tag_filter_button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    window.grid_tag_filter_menu = QMenu(window.grid_tag_filter_button)
    window.grid_tag_filter_button.setMenu(window.grid_tag_filter_menu)
    window.main_family_filter_button = QToolButton()
    window.main_family_filter_button.setText("Family")
    window.main_family_filter_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.main_family_filter_menu = QMenu(window.main_family_filter_button)
    window.main_family_filter_button.setMenu(window.main_family_filter_menu)
    window.attach_action_hint(
        window.main_family_filter_button,
        "Filter the main workflow by a command family or matching text tags.",
    )
    window.profile_button = QToolButton()
    window.profile_button.setText("Profiles")
    window.profile_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    window.profile_menu = QMenu(window.profile_button)
    window.profile_button.setMenu(window.profile_menu)
    window.attach_action_hint(window.profile_button, "Switch between isolated app profiles or create a new one.")
    grid_sort_layout.addSpacing(8)
    grid_sort_layout.addWidget(window.grid_tag_filter_button)
    grid_sort_layout.addStretch()

    window.grid_container = QWidget()
    window.grid_layout = FlowLayout(window.grid_container, spacing=12)
    window.grid_container.setLayout(window.grid_layout)

    window.grid_scroll = QScrollArea()
    window.grid_scroll.setWidgetResizable(True)
    window.grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
    window.grid_scroll.setWidget(window.grid_container)

    window.grid_page = QWidget()
    grid_page_layout = QVBoxLayout(window.grid_page)
    grid_page_layout.setContentsMargins(0, 0, 0, 0)
    grid_page_layout.setSpacing(8)
    grid_page_layout.addWidget(window.grid_sort_bar)
    grid_page_layout.addWidget(window.grid_scroll)

    window.table_page = QWidget()
    table_page_layout = QVBoxLayout(window.table_page)
    table_page_layout.setContentsMargins(8, 6, 8, 6)
    table_page_layout.setSpacing(0)
    table_page_layout.addWidget(window.table)

    window.view_stack = QStackedWidget()
    window.view_stack.addWidget(window.table_page)
    window.view_stack.addWidget(window.grid_page)


def build_main_window_shell(window: "NoteCopyPaster", main_window_module) -> None:
    container = QWidget()
    container.setObjectName("main-container")
    window.background_label = QLabel(container)
    window.background_label.hide()
    window.background_label.setScaledContents(False)
    window.background_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.background_label.setStyleSheet("background: transparent;")
    window.background_button = QToolButton()
    background_icon = main_window_module.image_icon(18)

    window.view_toggle_button = QToolButton()
    window.view_toggle_button.setAutoRaise(True)
    window.view_toggle_button.clicked.connect(window.toggle_view_mode)
    window.attach_action_hint(window.view_toggle_button, "Switch between table and grid views.")

    window.background_button.setIcon(background_icon)
    window.background_button.setAutoRaise(True)
    window.background_button.pressed.connect(window.presentation_controller.start_background_button_action)
    window.background_button.released.connect(window.presentation_controller.finish_background_button_action)
    window.attach_action_hint(window.background_button, window.background_button_hint)

    window.background_hold_timer = QTimer(window)
    window.background_hold_timer.setSingleShot(True)
    window.background_hold_timer.timeout.connect(window.clear_background_from_hold)

    window.widget_mode_button = QToolButton()
    window.widget_mode_button.setText("Widget")
    window.widget_mode_button.setCheckable(True)
    window.widget_mode_button.setAutoRaise(True)
    window.widget_mode_button.toggled.connect(window.toggle_widget_mode)
    window.attach_action_hint(
        window.widget_mode_button,
        "Toggle widget style — hides the top bar and column headers for a minimal look.",
    )

    window.widget_mode_options_button = QPushButton("Options")
    window.widget_mode_options_button.clicked.connect(window.settings_controller.show_options_dialog)
    window.widget_mode_options_button.hide()
    # widget_mode_bar is kept as a thin drag strip (no content) so the window
    # remains draggable from the top in widget mode.
    window.widget_mode_bar = QWidget()
    window.widget_mode_bar.setCursor(Qt.CursorShape.SizeAllCursor)
    window.widget_mode_bar.setFixedHeight(6)
    window.widget_mode_bar.installEventFilter(window)
    _wm_layout = QHBoxLayout(window.widget_mode_bar)
    _wm_layout.setContentsMargins(0, 0, 0, 0)
    _wm_layout.setSpacing(0)
    window.widget_mode_bar.hide()

    window.zoom_slider = QSlider(Qt.Orientation.Horizontal)
    window.zoom_slider.setRange(80, 140)
    window.zoom_slider.setValue(window.zoom_percent)
    window.zoom_slider.setFixedWidth(140)
    window.zoom_slider.valueChanged.connect(window.handle_zoom_changed)
    window.attach_action_hint(window.zoom_slider, "Zoom the interface text and buttons bigger or smaller.")

    build_terminal_toolbar_controls(window)

    window.add_selected_to_folder_button = QPushButton("Add Selected To Folder")
    window.add_selected_to_folder_button.clicked.connect(window.confirm_add_selected_to_folder)
    window.add_selected_to_folder_button.hide()
    window.attach_action_hint(
        window.add_selected_to_folder_button,
        "Move the currently checked items into the active target folder.",
    )

    window.cancel_add_to_folder_button = QPushButton("Cancel")
    window.cancel_add_to_folder_button.clicked.connect(window.cancel_add_to_folder_mode)
    window.cancel_add_to_folder_button.hide()
    window.attach_action_hint(
        window.cancel_add_to_folder_button,
        "Cancel add-to-folder selection mode.",
    )

    bottom_bar = QHBoxLayout()
    bottom_bar.setContentsMargins(0, 0, 0, 0)
    bottom_bar.addWidget(window.add_selected_to_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
    bottom_bar.addWidget(window.cancel_add_to_folder_button, 0, Qt.AlignmentFlag.AlignLeft)
    bottom_bar.addWidget(window.open_linked_terminal_button, 0, Qt.AlignmentFlag.AlignLeft)
    bottom_bar.addWidget(window.status_label, 1)
    bottom_bar.addWidget(window.zoom_slider, 0, Qt.AlignmentFlag.AlignRight)
    bottom_bar.addWidget(window.widget_mode_options_button, 0, Qt.AlignmentFlag.AlignRight)
    bottom_bar.addWidget(window.view_toggle_button, 0, Qt.AlignmentFlag.AlignRight)
    bottom_bar.addWidget(window.background_button, 0, Qt.AlignmentFlag.AlignRight)
    bottom_bar.addWidget(window.widget_mode_button, 0, Qt.AlignmentFlag.AlignRight)

    layout = QVBoxLayout()
    layout.addWidget(window.top_bar_widget)
    layout.addWidget(window.widget_mode_bar)
    layout.addWidget(window.search_results_widget)
    layout.addWidget(window.view_stack)
    layout.addWidget(window.terminal_toolbar_widget)
    layout.addLayout(bottom_bar)

    container.setLayout(layout)
    window.setCentralWidget(container)
    window.background_label.lower()

    window.resize_grips = []
    for _ in range(4):
        grip = QSizeGrip(window)
        grip.setFixedSize(18, 18)
        grip.setStyleSheet("background: transparent;")
        grip.hide()
        window.resize_grips.append(grip)
    window.update_move_window_button()


def build_main_window_ui(window: "NoteCopyPaster") -> None:
    from . import main_window as main_window_module

    window.status_label = QLabel()
    window.background_button_hint = "Click to set image background. Hold to default"
    window.search_input = QLineEdit()
    window.search_input.setPlaceholderText("Quick search files, content, and suggested commands...")
    window.search_input.textChanged.connect(window.search_controller.update_search_results)
    window.search_input.textChanged.connect(window.search_controller.handle_search_input_text_changed)
    window.search_input.installEventFilter(window)
    clear_action = window.search_input.addAction(
        main_window_module.search_clear_icon(16),
        QLineEdit.ActionPosition.LeadingPosition,
    )
    clear_action.triggered.connect(window.search_input.clear)

    window.undo_button = QPushButton("Undo")
    window.undo_button.clicked.connect(window.undo_last_action)
    window.undo_button.setEnabled(False)

    build_table_view(window)
    build_grid_view(window)
    build_search_results_widget(window)
    build_top_bar_controls(window, main_window_module)
    build_main_window_shell(window, main_window_module)


def build_window_overlays(window: "NoteCopyPaster") -> None:
    window.toast_label = QLabel(window)
    window.toast_label.hide()
    window.toast_label.setWordWrap(True)
    window.toast_label.setMaximumWidth(320)
    window.toast_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    window.toast_label.setStyleSheet(
        "QLabel {"
        "background-color: rgba(20, 20, 20, 220);"
        "color: white;"
        "border-radius: 10px;"
        "padding: 10px 14px;"
        "}"
    )

    window.hover_popup = QLabel(window)
    window.hover_popup.hide()
    window.hover_popup.setWindowFlag(Qt.WindowType.ToolTip, True)
    window.hover_popup.setWordWrap(True)
    window.hover_popup.setTextFormat(Qt.TextFormat.PlainText)

    window.instruction_banner = QLabel(window)
    window.instruction_banner.hide()
    window.instruction_banner.setWordWrap(True)
    window.instruction_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.instruction_banner.setMaximumWidth(540)
    window.instruction_banner.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    window.instruction_banner.setStyleSheet(
        "QLabel {"
        "background-color: rgba(12, 16, 20, 238);"
        "color: #f5f6f8;"
        "border: 1px solid rgba(255, 255, 255, 46);"
        "border-radius: 14px;"
        "padding: 18px 22px;"
        "font-size: 15px;"
        "}"
    )

    window.terminal_ai_overlay = QLabel(window)
    window.terminal_ai_overlay.hide()
    window.terminal_ai_overlay.setWordWrap(False)
    window.terminal_ai_overlay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    window.terminal_ai_overlay.setTextFormat(Qt.TextFormat.PlainText)
    window.terminal_ai_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    window.terminal_ai_overlay.setStyleSheet(
        "QLabel {"
        "background-color: rgba(10, 14, 18, 210);"
        "color: #f5f6f8;"
        "border: 1px solid rgba(255, 255, 255, 36);"
        "border-radius: 16px;"
        "padding: 8px 16px;"
        "font-size: 18px;"
        "font-weight: 600;"
        "font-family: monospace;"
        "}"
    )


def build_window_timers_and_shortcuts(window: "NoteCopyPaster") -> None:
    window.toast_timer = QTimer(window)
    window.toast_timer.setSingleShot(True)
    window.toast_timer.timeout.connect(window.toast_label.hide)

    window.hover_timer = QTimer(window)
    window.hover_timer.setSingleShot(True)
    window.hover_timer.timeout.connect(window.presentation_controller.show_pending_hover_popup)

    window.linked_terminal_timer = QTimer(window)
    window.linked_terminal_timer.timeout.connect(window.terminal_controller.refresh_linked_terminal_toolbar)
    window.linked_terminal_timer.start(650)
    window.auto_refresh_timer = QTimer(window)
    window.auto_refresh_timer.timeout.connect(window.view_controller.auto_refresh)
    window.auto_refresh_timer.start(2000)
    window.quick_search_sequence_timer = QTimer(window)
    window.quick_search_sequence_timer.setSingleShot(True)
    window.quick_search_sequence_timer.timeout.connect(window.search_controller.finish_pending_quick_search_action)
    window.search_inline_ai_timer = QTimer(window)
    window.search_inline_ai_timer.setSingleShot(True)
    window.search_inline_ai_timer.timeout.connect(window.search_controller.refresh_search_inline_ai_suggestion)
    window.terminal_inline_ai_timer = QTimer(window)
    window.terminal_inline_ai_timer.setSingleShot(True)
    window.terminal_inline_ai_timer.timeout.connect(window.terminal_controller.refresh_terminal_inline_ai_suggestion)

    undo_seq = QKeySequence(str(window.main_window_bindings.get("undo", ["Ctrl+Z", ""])[0]))
    window.undo_shortcut = QShortcut(undo_seq, window)
    window.undo_shortcut.activated.connect(window.undo_last_action)
    delete_seq = QKeySequence(str(window.main_window_bindings.get("delete_selected", ["Delete", ""])[0]))
    window.delete_shortcut = QShortcut(delete_seq, window.table)
    window.delete_shortcut.activated.connect(window.trash_selected_files)
    window.main_window_shortcuts = {"undo": window.undo_shortcut, "delete_selected": window.delete_shortcut}
