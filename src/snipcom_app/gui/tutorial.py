from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster

_TUTORIAL_DONE_KEY = "tutorial_done"

# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

_STEPS: list[dict[str, object]] = [
    {
        "title": "Start with the Command Store",
        "body": (
            "The Command Store is a catalog of shell commands you can download from "
            "curated GitHub repositories. Open it and click 'Recommended Repositories' "
            "to import hundreds of ready-to-use commands in one shot."
        ),
        "btn_label": "Open the Command Store",
        "action": lambda w: w.open_store_page(),
        # Wait for the store window to close before advancing
        "wait_widget": lambda w: w.store_window,
    },
    {
        "title": "Enable the AI assistant (optional)",
        "body": (
            "Snipcom can suggest commands using a local Ollama model - nothing leaves "
            "your machine. In Options > AI tab, tick 'Enable local AI', set your "
            "Ollama endpoint and model, and save."
        ),
        "btn_label": "Open Options",
        "action": lambda w: w.show_options_dialog(),
        "wait_widget": None,
    },
    {
        "title": "Create your first workflow file",
        "body": (
            "Your Workflow is your personal library of commands and snippets. "
            "Click New, name the file, and paste in a command you use often. "
            "It becomes instantly searchable, launchable, and sendable to any linked terminal."
        ),
        "btn_label": "Create a new file",
        "action": lambda w: w.workflow_controller.create_new_file(),
        "wait_widget": None,
    },
    {
        "title": "Link a terminal",
        "body": (
            "Click 'Open Terminal' (bottom-left) to launch a terminal that Snipcom "
            "can control. Once linked, 'Send Command' buttons pipe commands straight "
            "into it. The bottom bar is your control strip: left side for the terminal "
            "link, right side for quick actions on the selected entry."
        ),
        "btn_label": "Open a terminal session",
        "action": lambda w: w.open_linked_terminal_button.click(),
        "wait_widget": None,
    },
    {
        "title": "Zoom, grid/list, and Widget mode",
        "body": (
            "Bottom-right controls:\n"
            "- Slider: scale the UI up or down.\n"
            "- Grid/List toggle: switch between card grid and compact table.\n"
            "- Widget button: collapse the window to a frameless overlay you can "
            "keep visible on top of other apps. Click again to restore."
        ),
        "btn_label": None,
        "action": None,
        "wait_widget": None,
    },
    {
        "title": "Use Snipcom from any terminal",
        "body": (
            "The full feature set is available via the scm command:\n\n"
            "  scm              - interactive navigator\n"
            "  scm -find <q>    - search workflow and catalog\n"
            "  scm -f           - favourites\n"
            "  scm -help        - all commands\n\n"
            "Inside the navigator, type 'nat <request>' for AI suggestions."
        ),
        "btn_label": None,
        "action": None,
        "wait_widget": None,
    },
]


# ---------------------------------------------------------------------------
# Wait helper
# ---------------------------------------------------------------------------

def _wait_for_shown_then_hidden(
    get_widget: Callable[[], "QWidget | None"],
    callback: Callable[[], None],
) -> None:
    """Poll every 300 ms: first wait for the widget to become visible, then
    wait for it to hide, then call callback.  Handles the race where the
    widget hasn't appeared yet when the action fires."""
    timer = QTimer()
    timer.setInterval(300)
    _was_visible: list[bool] = [False]

    def _check() -> None:
        try:
            w = get_widget()
            visible = (w is not None) and w.isVisible()
        except RuntimeError:
            visible = False
        if not _was_visible[0]:
            if visible:
                _was_visible[0] = True
        else:
            if not visible:
                timer.stop()
                timer.deleteLater()
                callback()

    timer.timeout.connect(_check)
    timer.start()


# ---------------------------------------------------------------------------
# Tutorial dialog
# ---------------------------------------------------------------------------

class TutorialDialog(QDialog):
    """A single tutorial step card."""

    def __init__(
        self,
        window: "NoteCopyPaster",
        step_index: int,
        total_steps: int,
        on_action: Callable[[], None],
        on_skip: Callable[[], None],
    ) -> None:
        super().__init__(window, Qt.WindowType.Tool)
        step = _STEPS[step_index]
        self.setWindowTitle("Snipcom - Getting Started")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        # Fixed width so word-wrap computes a correct height
        self.setFixedWidth(500)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(10)

        # Step counter
        counter = QLabel("Step %d of %d" % (step_index + 1, total_steps))
        counter.setStyleSheet("color: rgba(180,180,180,0.75); font-size: 11px;")
        outer.addWidget(counter)

        # Title
        title_label = QLabel(str(step["title"]))
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setWordWrap(True)
        outer.addWidget(title_label)

        # Body
        body_label = QLabel(str(step["body"]))
        body_label.setWordWrap(True)
        body_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        outer.addWidget(body_label)

        outer.addSpacing(6)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        skip_btn = QPushButton("Skip step")
        skip_btn.setStyleSheet("color: rgba(180,180,180,0.75);")
        skip_btn.clicked.connect(on_skip)
        btn_row.addWidget(skip_btn)

        btn_row.addStretch(1)

        btn_label: object = step.get("btn_label")
        is_last = step_index + 1 >= total_steps
        if btn_label:
            action_text = str(btn_label)
        elif is_last:
            action_text = "Finish"
        else:
            action_text = "Got it  >"
        action_btn = QPushButton(action_text)
        action_btn.setDefault(True)
        action_btn.clicked.connect(on_action)
        btn_row.addWidget(action_btn)

        outer.addLayout(btn_row)

    def show_centered_on_parent(self) -> None:
        self.adjustSize()
        parent = self.parent()
        if parent is not None:
            pg = parent.geometry()  # type: ignore[attr-defined]
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + (pg.height() - self.height()) // 3
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()


# ---------------------------------------------------------------------------
# Tutorial runner
# ---------------------------------------------------------------------------

def run_tutorial(window: "NoteCopyPaster") -> None:
    """Show tutorial steps in sequence starting from step 0."""
    total = len(_STEPS)
    # Keep strong Python references so WA_DeleteOnClose is NOT needed and
    # the C++ objects stay alive until we explicitly close them.
    dialogs: list[TutorialDialog] = []
    _done = [False]

    def mark_done() -> None:
        if _done[0]:
            return
        _done[0] = True
        window.settings[_TUTORIAL_DONE_KEY] = True
        window.save_settings()

    def close_all() -> None:
        for d in list(dialogs):
            try:
                d.close()
            except RuntimeError:
                pass
        dialogs.clear()

    def show_step(index: int) -> None:
        if index >= total:
            mark_done()
            return

        step = _STEPS[index]
        action: object = step.get("action")
        wait_widget_fn: object = step.get("wait_widget")

        def on_action() -> None:
            dlg.hide()

            if callable(action):
                try:
                    action(window)  # type: ignore[operator]
                except Exception:
                    pass

            # If the action opens a persistent window, wait until it appears
            # then disappears before advancing (handles async window creation).
            if callable(wait_widget_fn):
                _wait_for_shown_then_hidden(
                    lambda: wait_widget_fn(window),  # type: ignore[operator]
                    _advance,
                )
            else:
                QTimer.singleShot(300, _advance)

        def _advance() -> None:
            try:
                dialogs.remove(dlg)
            except ValueError:
                pass
            try:
                dlg.close()
            except RuntimeError:
                pass
            show_step(index + 1)

        def on_skip() -> None:
            # Skip this step and move to the next one.
            _advance()

        dlg = TutorialDialog(window, index, total, on_action=on_action, on_skip=on_skip)
        dialogs.append(dlg)
        dlg.show_centered_on_parent()

    show_step(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def maybe_show_tutorial(window: "NoteCopyPaster", *, force: bool = False) -> None:
    """Show the tutorial if this is the first run (or if force=True)."""
    if not force and window.settings.get(_TUTORIAL_DONE_KEY):
        return
    QTimer.singleShot(600, lambda: run_tutorial(window))
