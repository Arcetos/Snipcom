---
paths:
  - "src/snipcom_app/cli/**"
---

# cli
- Purpose: CLI interface, dispatched from entrypoint.py when launcher name is `scm` or args are present.
- Key entrypoints: `cli.py`, `cli_context.py`, `cli_entries.py`, `cli_nav.py`, `cli_shell.py`
- Dependencies: `..core.*`, `..ai.*`, `..integration.*`; siblings for each other
- Hot files: `cli.py` (command dispatch), `cli_entries.py` (entry operations)
- Invariants: no PyQt6 imports; entrypoint dispatch in `entrypoint.py` at root
- Avoid reading: `__pycache__/`
