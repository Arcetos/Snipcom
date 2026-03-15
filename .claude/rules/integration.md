---
paths:
  - "src/snipcom_app/integration/**"
---

# integration
- Purpose: Linked terminal, desktop integration, import/export, git source sync.
- Key entrypoints: `linked_terminal.py`, `desktop_integration.py`, `importers.py`, `source_sync.py`, `import_source_catalog.py`
- Dependencies: `..core.*` for helpers/repository; siblings for each other; no PyQt6 at module level
- Hot files: `importers.py` (import/export formats), `source_sync.py` (git sync/stale purge), `linked_terminal.py` (terminal behavior)
- Invariants: catalog-only entries (`catalog_only=True`) must never appear in main workflow unless promoted
- Avoid reading: `__pycache__/`
