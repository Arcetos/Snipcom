---
paths:
  - "src/snipcom_app/ai/**"
---

# ai
- Purpose: AI provider protocol and app-level AI controller — no Qt, no display required.
- Key entrypoints: `ai.py` (provider protocol), `ai_shared.py` (shared helpers), `ai_controller.py` (app context, imports generate_ollama_command from integration)
- Dependencies: sibling relative imports only (`.ai`, `.ai_shared`) — no PyQt6
- Hot files: `ai_controller.py`, `ai.py`
- Invariants: must remain importable without a display; never import PyQt6 here
- Avoid reading: `__pycache__/`
