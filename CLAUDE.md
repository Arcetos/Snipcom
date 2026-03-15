# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Install to local bin (required before testing):**
```bash
bash scripts/install-local.sh
```
Copies sources to `~/.local/bin/snipcom_app/` and installs launchers at `~/.local/bin/{snipcom,scm}`.

**Quick syntax check (without installing):**
```bash
python3 -m py_compile src/snipcom_app/<file>.py
```

**Runtime import verifier (catches what py_compile misses):**
```bash
bash scripts/verify-imports.sh
```
Imports every module in the package tree; catches missing re-exports, import-time attribute errors, and circular imports.

**CLI smoke tests (after install):**
```bash
scm --help                      # must print custom help, exit 0
scm -find __nonexistent_xyz__   # must exit 0 (empty results, no crash)
scm -f                          # must list favorites or show empty, exit 0
scm -w                          # must list workspace or show empty, exit 0
```

**Offscreen GUI smoke test (after install):**
```bash
timeout 8s env QT_QPA_PLATFORM=offscreen ~/.local/bin/snipcom
```
Exit code 0 or 124 (timeout) both mean success.

> Note: `scripts/dev-smoke.sh` references the old flat package layout and is outdated — use the commands above directly.

There is no formal test suite (no pytest, tox, or pyproject.toml).

## Architecture

See `ARCHITECTURE.md` for the full picture. Summary:

The app has two surfaces:
- **Main workflow window** — active text files and family commands (the everyday UX)
- **Store window** — catalog browser for imported command sets from git repos

**Entrypoint dispatch** (`entrypoint.py`): launcher name `scm` → CLI; otherwise → GUI. Running with any args also routes to CLI.

**Two storage backends:**
- `text_file` entries — real files under the user's texts root (`~/.local/share/snipcom/texts/` by default)
- `family_command` entries — SQLite records in `{texts_root}/.snipcom/commands.sqlite3`

**Catalog isolation:** Imported commands live with `catalog_only=True` and never appear in the main workflow unless explicitly promoted.

## Key Conventions

**Module headers:** Every `.py` file starts with a docstring declaring what it contains and what is NOT there. Keep these updated when modifying a file — they are the primary navigation aid for AI agents.

**Import paths by layer** (violations break the dependency graph):
- `core/` → sibling relative only
- `ai/` → sibling relative only (no Qt)
- `integration/` → `..core.*` + siblings
- `cli/` → `..core.*`, `..ai.*`, `..integration.*`, siblings
- `gui/` mixins → `..core.*`, `..integration.*`, `..ai.*`, siblings
- `gui/controllers/` → `...core.*`, `...ai.*`, `...integration.*`; `..main_window` under `TYPE_CHECKING` only
- `gui/workflow/` → `...core.*`, `...integration.*`; `..main_window` under `TYPE_CHECKING` only
- `core/` and `ai/` must remain importable without a display (no PyQt6 imports)

**Status messages in GUI:**
- `show_feedback(msg)` — status bar + toast together (use when both should say the same thing)
- `show_status(msg)` + `show_toast(msg2)` — use when messages intentionally differ

**Useful helpers in `core/helpers.py`:**
- `read_json_file(path)` — safe JSON dict load, returns `{}` on any error
- `normalize_launch_options(opts)` — normalizes keep_open/ask_extra/copy_output dict; call directly, no wrappers

## Where To Edit Common Changes

| Change | Files |
|--------|-------|
| Workflow action (rename, tag, copy, send) | `gui/controllers/workflow_controller.py`, `gui/controllers/terminal_controller.py` |
| Table / grid appearance | `gui/widgets.py`, `gui/controllers/view_controller.py` |
| Data storage or metadata format | `core/repository.py`, `core/command_store.py` |
| Import / export formats | `integration/importers.py` + `gui/windows/store_window.py` |
| AI behavior | `ai/ai_controller.py` (app context), `ai/ai.py` (provider protocol) |
| Quick search ranking | `gui/controllers/search_controller.py` |
| Linked terminal behavior | `gui/controllers/terminal_controller.py`, `integration/linked_terminal.py` |
| Store window UI | `gui/windows/store_window.py` |
| Git source sync / stale purge | `integration/source_sync.py` |

## Known Structural Debt

- `gui/main_window.py` still has legacy globals `TEXTOS_DIR` / `set_texts_dir()` that are mutated at runtime on profile switch — scheduled for cleanup to instance fields.
- `app.py` owns startup migrations and seeding; it should not grow into a runtime controller.
