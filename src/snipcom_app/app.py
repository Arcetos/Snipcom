from __future__ import annotations

import shutil
import sys

from PyQt6.QtWidgets import QApplication

_FORCE_TUTORIAL = "--tutorial" in sys.argv

from .integration.import_source_catalog import IMPORT_SOURCES_ROOT
from .integration.importers import import_cheatsheets, import_navi_cheats
from .gui.main_window import NoteCopyPaster
from .startup_compat import (
    migrate_imported_command_titles,
    migrate_workflow_clone_suffixes,
    remove_legacy_demo_data,
)
from .gui.windows.store_window import StoreWindow


def _native_package_manager_cheatsheet(import_root) -> list:
    """Return cheatsheet paths for the package manager(s) available on this system."""
    cheat_dir = import_root / "cheat-cheatsheets"
    # Ordered by detection priority; include the main PM and its low-level companion where useful
    candidates = [
        ("apt", ["apt", "dpkg"]),
        ("pacman", ["pacman"]),
        ("zypper", ["zypper"]),
        ("dnf", ["dnf", "rpm"]),
        ("yum", ["yum", "rpm"]),
        ("apk", ["apk"]),
    ]
    for pm_executable, cheat_names in candidates:
        if shutil.which(pm_executable):
            return [cheat_dir / name for name in cheat_names]
    # Final fallback: rpm is always present on RHEL/Fedora
    return [cheat_dir / "rpm"]


def seed_curated_catalog(window: NoteCopyPaster) -> None:
    import_root = IMPORT_SOURCES_ROOT
    curated_navi_files = [
        import_root / "denisidoro-cheats" / "code" / "git.cheat",
        import_root / "denisidoro-cheats" / "misc" / "systemctl.cheat",
        import_root / "denisidoro-cheats" / "misc" / "shell.cheat",
    ]
    curated_cheat_files = [
        *_native_package_manager_cheatsheet(import_root),
        import_root / "cheat-cheatsheets" / "journalctl",
    ]

    if any(str(batch.get("label", "")) == "Starter Catalog" for batch in window.repository.list_import_batches()):
        return

    payloads = []
    for path in curated_navi_files:
        if path.exists():
            payloads.append(import_navi_cheats(path, source_license="CC0-1.0"))
    for path in curated_cheat_files:
        if path.exists():
            payloads.append(import_cheatsheets(path, source_license="CC0-1.0"))
    if not payloads:
        return

    commands = []
    for payload in payloads:
        commands.extend(payload.commands)
    if not commands:
        return

    batch_id = window.repository.create_import_batch(
        label="Starter Catalog",
        source_kind="starter-catalog",
        source_ref="local curated presets",
        source_license="CC0-1.0",
        summary={"command_count": len(commands), "family_count": len({command.family_key for command in commands if command.family_key})},
    )
    imported = 0
    for command in commands:
        title = window.repository.unique_command_title(command.title)
        window.repository.command_store.create_command(
            title,
            body=command.body,
            snip_type=command.snip_type,
            family_key=command.family_key,
            description=command.description,
            source_kind=command.source_kind,
            source_ref=command.source_ref,
            source_license=command.source_license,
            import_batch_id=batch_id,
            catalog_only=True,
            dangerous=False,
            tags=list(command.tags),
            extra=dict(command.extra),
        )
        imported += 1
    if imported:
        window.refresh_table()
        window.update_search_results()
        window.show_status(f"Seeded starter catalog with {imported} imported commands.")


def main() -> int:
    app = QApplication(sys.argv)
    window = NoteCopyPaster()
    if getattr(window, "startup_aborted", False):
        return 0
    remove_legacy_demo_data(window)
    seed_curated_catalog(window)
    migrate_imported_command_titles(window)
    migrate_workflow_clone_suffixes(window)
    store_window = StoreWindow(window)
    window.store_window = store_window
    window.show()

    from .gui.tutorial import maybe_show_tutorial
    maybe_show_tutorial(window, force=_FORCE_TUTORIAL)

    return app.exec()
