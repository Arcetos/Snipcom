---
paths:
  - "src/snipcom_app/gui/**"
---

# gui
- Purpose: PyQt6 GUI — main workflow window and store window.
- Key entrypoints: `main_window.py` (legacy globals TEXTOS_DIR / set_texts_dir() — scheduled cleanup), `main_window_layout.py`, `widgets.py`
- Mixins (extend main_window): `main_window_*_mixin.py` (dialog, entry, history, interaction, presentation, state, table, ui, workflow)
- Controllers (`gui/controllers/`): `workflow_controller.py`, `terminal_controller.py`, `search_controller.py`, `view_controller.py`, `settings_controller.py`, `presentation_controller.py`, `profile_state_controller.py`, `ai_controller.py`
- Workflow (`gui/workflow/`): `workflow_entry_actions.py`, `workflow_entry_content.py`, `workflow_folder_popup.py`, `workflow_terminal_actions.py`
- Windows (`gui/windows/`): `store_window.py`
- Dependencies: mixins use `..core.*`, `..integration.*`, `..ai.*`, siblings; controllers use `...core.*`, `...ai.*`, `...integration.*`; `..main_window` under TYPE_CHECKING only
- Status helpers: `show_feedback(msg)` = status bar + toast (defined in `main_window_presentation_mixin.py`); use `show_status` + `show_toast` only when messages intentionally differ
- Hot files: `workflow_controller.py`, `terminal_controller.py`, `search_controller.py`, `widgets.py`
- Avoid reading: `__pycache__/`
