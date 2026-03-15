from __future__ import annotations

from pathlib import Path

from .cli_context import APP_SUPPORT_DIR


def _shell_script(shell_name: str) -> str:
    if shell_name == "bash":
        return r"""
# Ctrl+G: open interactive navigator and insert selection into readline buffer
__snipcom_pick_insert() {
  local query="$READLINE_LINE"
  local picked
  picked="$(command scm -nav "$query")" || return
  [ -n "$picked" ] || return
  READLINE_LINE="$picked"
  READLINE_POINT=${#READLINE_LINE}
}
case "$-" in
  *i*) bind -x '"\C-g":__snipcom_pick_insert' ;;
esac
# Note: "scm <name>" cannot replace the readline buffer on Enter in bash —
# readline state is consumed before any shell function runs. Use Ctrl+G instead.""".strip()
    if shell_name == "zsh":
        return r"""
# Ctrl+G: open interactive navigator and insert selection into zsh prompt
function snipcom_pick_insert() {
  local query="$LBUFFER $RBUFFER"
  local picked
  picked="$(command scm -nav "$query")" || return
  [[ -n "$picked" ]] || return
  LBUFFER="$picked"
}
zle -N snipcom_pick_insert
bindkey '^G' snipcom_pick_insert

# Override accept-line: if the buffer is "scm <name>", expand it instead of running it.
# The expanded command is placed back into the buffer; press Enter again to execute.
function __snipcom_accept_line() {
  if [[ "$BUFFER" =~ ^scm[[:space:]]+[^-] ]]; then
    local _args="${BUFFER#scm }"
    local _out
    _out="$(command scm ${=_args} 2>/dev/null)"
    if [[ $? -eq 0 && -n "$_out" ]]; then
      BUFFER="$_out"
      CURSOR=${#BUFFER}
      zle redisplay
      return 0
    fi
  fi
  zle accept-line
}
zle -N __snipcom_accept_line
bindkey '^M' __snipcom_accept_line
bindkey '^J' __snipcom_accept_line""".strip()
    if shell_name == "fish":
        return """
function snipcom_pick_insert
    set -l query (commandline -b)
    set -l picked (command scm -nav "$query")
    if test -n "$picked"
        commandline -r -- "$picked"
    end
end
bind \\cg snipcom_pick_insert
""".strip()
    raise ValueError(f"Unsupported shell: {shell_name}")


def _shell_install(shell_name: str) -> int:
    shell_dir = APP_SUPPORT_DIR / "shell"
    shell_dir.mkdir(parents=True, exist_ok=True)
    snippet_path = shell_dir / f"snipcom-{shell_name}.sh"
    snippet_path.write_text(_shell_script(shell_name) + "\n", encoding="utf-8")
    if shell_name == "fish":
        rc_path = Path.home() / ".config" / "fish" / "conf.d" / "snipcom.fish"
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        source_line = f'test -f "{snippet_path}" ; and source "{snippet_path}"'
    else:
        rc_path = Path.home() / (".bashrc" if shell_name == "bash" else ".zshrc")
        source_line = f'[ -f "{snippet_path}" ] && source "{snippet_path}"'
    rc_text = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
    if source_line not in rc_text:
        with rc_path.open("a", encoding="utf-8") as handle:
            if rc_text and not rc_text.endswith("\n"):
                handle.write("\n")
            handle.write(f"\n# Snipcom shell integration\n{source_line}\n")
    print(f"Installed {shell_name} integration at {snippet_path}")
    print(f"Restart your shell or run: source {rc_path}")
    return 0
