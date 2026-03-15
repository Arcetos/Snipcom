# Snipcom Architecture

## Purpose
This document is the fastest way to understand the project and know where to edit
without reading the whole codebase.

The application has two first-class surfaces:
- the main workflow window for active text files and family commands
- the store window for imported catalog commands

The app is local-first:
- `text_file` entries are real files under the selected texts root
- `family_command` entries are SQLite records under `.snipcom/`

## Package Layout

```
src/snipcom_app/
├── app.py                  Qt startup, migrations, starter seeding, window boot
├── entrypoint.py           GUI/CLI dispatch (thin shim)
├── startup_compat.py       One-time startup migrations
│
├── core/                   Data models, storage, pure helpers
│   ├── app_state.py        ProfileUiState dataclass
│   ├── command_store.py    SQLite schema, CRUD, import batches, usage history
│   ├── helpers.py          Pure helpers: text detection, path, tags, JSON I/O
│   ├── profiles.py         Profile registry and filesystem layout
│   ├── repository.py       Unified entry model, file/DB operations, metadata
│   ├── safety.py           Command risk evaluation
│   └── snip_types.py       Snip-type constants and labels
│
├── ai/                     AI provider layer (no Qt, no runtime state)
│   ├── ai.py               Ollama connectivity, prompt building, sanitization
│   ├── ai_controller.py    App-level AI behavior, context building, ranking
│   └── ai_shared.py        Shared AI config helpers (GUI + CLI)
│
├── integration/            External service integrations
│   ├── desktop_integration.py  Terminal launch, file opener fallbacks
│   ├── import_source_catalog.py  Predefined import source list
│   ├── importers.py        JSON/Navi/cheatsheet parsers and export adapters
│   ├── linked_terminal.py  Tmux session lifecycle, command dispatch
│   └── source_sync.py      Git sync for import sources
│
├── cli/                    CLI entry surface
│   ├── cli.py              Argument parsing, top-level CLI handlers
│   ├── cli_context.py      CLI context object, profile/repo setup
│   ├── cli_entries.py      Entry lookup, preview, text reading
│   ├── cli_nav.py          Navigator UI, candidate ranking, interactive selection
│   └── cli_shell.py        Shell completion installation
│
└── gui/                    Qt6 GUI
    ├── main_window.py      Composition root, constants, global path helpers
    ├── main_window_layout.py  Layout constants and assembly helpers
    ├── main_window_*_mixin.py  Window behavior split into focused mixins
    ├── widgets.py          Custom table delegate, grid cards, flow layout
    │
    ├── controllers/        Controller objects wired to the main window
    │   ├── ai_controller.py
    │   ├── presentation_controller.py
    │   ├── profile_state_controller.py
    │   ├── search_controller.py
    │   ├── settings_controller.py
    │   ├── terminal_controller.py
    │   ├── view_controller.py
    │   └── workflow_controller.py
    │
    ├── windows/            Secondary Qt windows
    │   └── store_window.py  Catalog browser, import/export UI
    │
    └── workflow/           Workflow helper modules (called from main window mixin)
        ├── workflow_entry_actions.py   Rename, tag, favorite operations
        ├── workflow_entry_content.py   Content editing, clipboard
        ├── workflow_folder_popup.py    Folder editing popup
        └── workflow_terminal_actions.py  Terminal send, output capture
```

## Core Runtime Flows

### 1. Active workflow entry rendering
1. `gui/main_window.py` creates the UI shell.
2. `gui/controllers/view_controller.py` requests filtered/sorted entries from the repository.
3. `core/repository.py` returns a unified `SnipcomEntry` list from text files and non-catalog command records.

### 2. Store/catalog browsing
1. `gui/windows/store_window.py` queries `repository.catalog_entries()`
2. imported commands remain `catalog_only=True`
3. store actions promote a catalog command into the workflow rather than mutating the original

### 3. Linked terminal flow
1. `gui/controllers/terminal_controller.py` chooses/creates a session
2. `integration/linked_terminal.py` owns the runtime directory and delivery files
3. last command/output are read back; `ai/ai_controller.py` and terminal suggestions consume that context

### 4. Profiles
1. `gui/controllers/profile_state_controller.py` asks `core/profiles.py` for paths
2. `UiStateController` hydrates and saves profile-scoped UI state
3. repository root is switched to the profile texts root

## Where To Edit Common Changes

### Add or change a workflow action
- `gui/controllers/workflow_controller.py` or `gui/controllers/terminal_controller.py`
- rendering hooks in `gui/controllers/view_controller.py` or `gui/widgets.py` only if needed

### Change list/grid appearance
- `gui/widgets.py`
- `gui/controllers/view_controller.py`

### Change data storage or metadata format
- `core/repository.py`
- `core/command_store.py`
- maybe `core/profiles.py` if the storage location changes

### Add import/export formats
- `integration/importers.py`
- then wire UI in `gui/windows/store_window.py`

### Improve AI behavior
- `ai/ai_controller.py` for app-specific context/rules
- `ai/ai.py` for provider protocol and endpoint behavior

### Change quick search behavior
- `gui/controllers/search_controller.py`

### Change linked terminal behavior
- `gui/controllers/terminal_controller.py`
- `integration/linked_terminal.py` for runtime/session details

## Important Invariants
- `text_file` stays file-backed.
- `family_command` is DB-backed.
- imported catalog commands do not appear in the main workflow unless explicitly promoted.
- profiles must behave like separate local users.
- AI is optional; the app must remain fully usable with AI off.
- `ai/` and `core/` have no Qt dependency — they are importable without a display.

## Current Structural Notes
- `gui/main_window.py` still contains legacy compatibility globals for the active texts
  root (`TEXTOS_DIR`, `set_texts_dir()`). These are mutated at runtime when the user
  switches roots. Moving them to instance fields is a future clean-up task.
- `app.py` owns startup migrations and starter seeding; it should not grow into a
  second runtime controller layer.
