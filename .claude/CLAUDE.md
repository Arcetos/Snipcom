# snipcom-packaging

## Operating mode
- Keep answers terse; max 5 bullets unless asked for more.
- Prefer targeted Glob/Grep/Read over broad repo scans.
- Do not read large files end-to-end unless required.
- Do not paste large code blocks; cite file paths instead.
- Before editing, identify the smallest affected subtree and stay inside it.
- For exploration, use /repo-scout <path> first.
- When the task changes to another package/area, suggest /clear or /compact.

## Validation
- Syntax check: `python3 -m py_compile src/snipcom_app/<file>.py`
- Install + smoke test: `bash scripts/install-local.sh && timeout 8s env QT_QPA_PLATFORM=offscreen ~/.local/bin/snipcom`
- Exit code 0 or 124 (timeout) both mean success.
- Run the smallest command that proves the change.
- Avoid generated/build/vendor directories unless explicitly required.

## Important
- Do not import large files into this file with @README / @package.json / etc.
- Put area-specific instructions in .claude/rules/*.md with path scoping.
