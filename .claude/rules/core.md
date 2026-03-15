---
paths:
  - "src/snipcom_app/core/**"
---

# core
- Purpose: Data models, storage backends, helpers — no Qt, no display required.
- Key entrypoints: `repository.py` (text_file entries), `command_store.py` (family_command SQLite entries), `helpers.py` (read_json_file, normalize_launch_options), `snip_types.py` (type defs), `profiles.py`, `app_state.py`, `safety.py`
- Dependencies: sibling relative imports only (`.helpers`, `.repository`, etc.) — no PyQt6, no integration, no ai
- Hot files: `repository.py`, `command_store.py`, `helpers.py`
- Invariants: must remain importable without a display; never import PyQt6 here
- Avoid reading: `__pycache__/`
