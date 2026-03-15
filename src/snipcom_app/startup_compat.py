from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .gui.main_window import NoteCopyPaster


def remove_legacy_demo_data(window: "NoteCopyPaster") -> None:
    demo_file_names = {"release_notes.txt", "git_workflow.txt", "crash_notes.txt"}
    demo_titles = {
        "git status quick",
        "show package history",
        "inspect installed package",
        "list crash directory",
        "show current directory",
        "git pull with rebase",
        "show logs in current folder",
    }

    removed_any = False
    for file_name in demo_file_names:
        path = window.repository.resolve_text_file_path(file_name, fallback_suffix=".txt")
        if not path.exists():
            continue
        window.repository.remove_metadata(window.tags, window.snip_types, window.launch_options, path)
        path.unlink()
        removed_any = True

    for record in list(window.repository.command_store.list_commands(include_trashed=True)):
        if record.source_kind == "demo-catalog" or record.title in demo_titles:
            window.repository.command_store.delete_command(record.command_id)
            removed_any = True

    for batch in window.repository.list_import_batches():
        if str(batch.get("label", "")) == "Demo Catalog":
            window.repository.command_store.delete_import_batch(int(batch["id"]))
            removed_any = True

    if removed_any:
        window.save_tags()
        window.save_snip_types()
        window.save_launch_options()
        window.refresh_table()


def migrate_imported_command_titles(window: "NoteCopyPaster") -> None:
    migrated = 0
    for record in window.repository.command_store.list_commands(include_trashed=True):
        if record.source_kind not in {"navi-cheat", "cheatsheet"}:
            continue
        body_first_line = next((line.strip() for line in record.body.splitlines() if line.strip()), "")
        if not body_first_line or record.title == body_first_line:
            continue
        new_title = window.repository.unique_command_title(body_first_line, exclude_id=record.command_id)
        new_description = record.description.strip() or record.title.strip()
        window.repository.command_store.update_command(
            record.command_id,
            title=new_title,
            description=new_description,
        )
        migrated += 1

    if migrated:
        window.refresh_table()
        window.update_search_results()
        window.show_status(f"Updated {migrated} imported commands to use command text as the title.")


def migrate_workflow_clone_suffixes(window: "NoteCopyPaster") -> None:
    renamed = 0
    catalog_titles = {
        record.title.casefold()
        for record in window.repository.command_store.list_commands(catalog_only=True)
    }
    suffix_pattern = re.compile(r"^(?P<base>.+?)\s+(?P<number>\d+)$")
    for record in window.repository.command_store.list_commands(catalog_only=False):
        match = suffix_pattern.match(record.title.strip())
        if not match:
            continue
        base_title = match.group("base").strip()
        if base_title.casefold() not in catalog_titles:
            continue
        suffix_prefix = "fam"
        candidate_index = 1
        while True:
            candidate_title = f"{base_title} - {suffix_prefix}{candidate_index}"
            if not window.repository.workflow_command_title_exists(candidate_title, exclude_id=record.command_id):
                break
            candidate_index += 1
        window.repository.command_store.update_command(record.command_id, title=candidate_title)
        renamed += 1

    if renamed:
        window.refresh_table()
        window.update_search_results()
        window.show_status(f"Updated {renamed} workflow command names to the new suffix format.")
