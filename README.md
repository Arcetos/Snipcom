# Snipcom

A local-first desktop utility for organising shell commands, text snippets, and reusable workflows in one place — with a full-featured terminal companion (`scm`).

![Snipcom](assets/io.github.arcetos.Snipcom.svg)

---

## Features

### GUI (main window)
- **Workflow table / grid view** — browse, search, and manage your commands and text files in a sortable table or a card grid.
- **Widget mode** — collapse to a compact, always-on-top frameless overlay while you work in other apps.
- **Linked terminal** — open a tmux session that Snipcom controls. Send any command directly from the workflow with one click.
- **Command Store** — import hundreds of ready-to-use shell commands from curated GitHub repositories (navi cheats, cheat cheatsheets, and more). Imported commands are kept in a separate catalog and never clutter your personal workflow.
- **AI assistant (optional)** — integrates with a local [Ollama](https://ollama.com) model. Generates command suggestions without sending anything off your machine.
- **Tags, descriptions, snip types** — annotate every entry for fast filtering.
- **Trash & undo** — soft-delete with a recoverable trash bin; undo the last destructive action.
- **Multiple profiles** — separate workspaces, each with their own texts directory and settings.

### CLI (`scm`)
- **Interactive navigator** — full-screen TUI with three sections: heuristic suggestions, AI-generated commands, and your personal workflow. Type to filter live; press Tab to load a command for editing before running it.
- **Ghost suggestions** — the top candidate is shown as a dim hint in the input line; Shift+Tab to accept it instantly.
- **`nat <request>`** — type a natural-language request inside the navigator (e.g. `nat list files by size then delete the biggest`) and Ollama generates a compound shell command on the spot.
- **`scm -w`** — workspace listing as an aligned table: name, command, description.
- **`scm -f`** — favourites list.
- **`scm -find <query>`** — full-text search across workflow and catalog.
- **`scm -new`** — interactively create a new text file or a personal command (saved to JSON).
- **`scm -s <name>`** — preview an entry with metadata.
- **`scm nat <request>`** — standalone AI suggestion outside the navigator.
- **Shell integration** — `scm shell install bash` / `zsh` adds a Ctrl+G keybind that opens the navigator directly from your prompt.
- **Customisable key bindings** — navigator keys configurable from Options → Key Bindings.

---

## Requirements

| Dependency | Version |
|---|---|
| Python | 3.11 or newer |
| PyQt6 | 6.4 or newer |
| tmux | any recent version (for linked terminal) |
| git | any (for Command Store sync) |
| Ollama | optional (for AI suggestions) |

Install Python dependencies:

```bash
pip install PyQt6
```

---

## Installation

### Local install (recommended for development / daily use)

```bash
git clone https://github.com/arcetos/snipcom.git
cd snipcom
bash scripts/install-local.sh
```

This copies the app to `~/.local/bin/snipcom_app/` and places two launchers:

- `~/.local/bin/snipcom` — opens the GUI
- `~/.local/bin/scm` — opens the terminal companion

Make sure `~/.local/bin` is in your `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Verify the install

```bash
snipcom --version     # launch GUI (or offscreen check below)
scm --help            # print CLI help
scm -w                # list workspace (empty on first run)
```

Offscreen GUI smoke test (no display required):

```bash
timeout 8s env QT_QPA_PLATFORM=offscreen snipcom
# exit 0 or 124 = success
```

---

## Quick start

### 1. Open Snipcom

```bash
snipcom
```

### 2. Import commands from the Command Store

Click **Store** in the top bar → **Recommended Repositories** → tick what you want → **Import Selected**.

Imported commands appear in the **AI / heuristic** section of the `scm` navigator and never mix into your personal workflow unless you promote them.

### 3. Create a personal command

**From the GUI:** click **New** → choose **Command** → fill in title, body, and description.

**From the CLI:**

```bash
scm -new
# Choose: 1) Text file  2) Command
# Enter title, body, and optional description
```

Personal commands are saved to `~/.local/share/snipcom/texts/.snipcom/my_commands.json`.

### 4. Use the navigator

```bash
scm
```

| Key | Action |
|---|---|
| Type | Filter candidates live |
| Up / Down | Move between entries |
| Left / Right | Switch sections (Heuristic / AI / Workflow) |
| Enter | Execute highlighted entry |
| Tab | Load entry into input for editing, then Enter to run |
| Shift+Tab | Accept ghost suggestion |
| Alt+S | (in edit mode) Save loaded command as a new workflow file |
| Esc | Exit navigator |

### 5. AI suggestions

Enable Ollama in **Options → AI** (tick *Enable local AI*, set endpoint and model name).

Inside the navigator, prefix your query with `nat`:

```
nat find all log files modified in the last 7 days and compress them
```

Or from the shell directly:

```bash
scm nat "list docker containers sorted by memory usage"
```

### 6. Link a terminal

Click **Open Terminal** in the bottom-left of the main window. Snipcom will launch a tmux session it can control. Once linked, every entry has a **Send** button that pipes the command straight into the terminal.

---

## Data locations

| Path | Contents |
|---|---|
| `~/.local/share/snipcom/texts/` | Your workflow text files |
| `~/.local/share/snipcom/texts/.snipcom/commands.sqlite3` | Catalog (imported) commands |
| `~/.local/share/snipcom/texts/.snipcom/my_commands.json` | User-created commands |
| `~/.local/share/snipcom/texts/.snipcom/tags.json` | Tag assignments |
| `~/.local/share/snipcom/texts/.snipcom/descriptions.json` | Entry descriptions |
| `~/.config/snipcom/settings.json` | App settings |

---

## Development

```bash
# Syntax check a single file
python3 -m py_compile src/snipcom_app/<file>.py

# Verify all module imports (catches import-time errors)
bash scripts/verify-imports.sh

# Install and run CLI smoke tests
bash scripts/install-local.sh
scm --help
scm -find __nonexistent_xyz__
scm -f
scm -w

# Offscreen GUI smoke test
timeout 8s env QT_QPA_PLATFORM=offscreen ~/.local/bin/snipcom
```

See `ARCHITECTURE.md` for a full map of the codebase.

---

## License

See `flatpak/io.github.arcetos.Snipcom.metainfo.xml` for project license information.
