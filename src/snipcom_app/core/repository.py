from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .command_store import CommandRecord, CommandStore, ImportSourceRecord, normalize_command_snip_type
from .helpers import available_path, is_text_file, join_tags, normalize_launch_options, read_json_file
from .repository_metadata import RepositoryMetadataMixin
from .user_command_store import UserCommandStore


COMMAND_BACKUPS_DIRNAME = "command-backups"


@dataclass(frozen=True)
class SnipcomEntry:
    entry_id: str
    backend: str
    name: str
    display_name: str
    snip_type: str
    tag_text: str
    size_bytes: int
    modified_timestamp: float
    dangerous: bool = False
    family_key: str = ""
    catalog_only: bool = False
    import_batch_id: int = 0
    source_kind: str = ""
    source_ref: str = ""
    source_license: str = ""
    path: Path | None = None
    command_id: int | None = None
    folder_mode: str = ""
    description: str = ""
    body: str = ""

    @property
    def is_file(self) -> bool:
        return self.backend == "file"

    @property
    def is_command(self) -> bool:
        return self.backend in ("command", "json_command")

    @property
    def is_folder(self) -> bool:
        return self.backend == "folder"


class SnipcomRepository(RepositoryMetadataMixin):
    VALID_SNIP_TYPES = {"text_file", "family_command"}
    FOLDER_META_FILENAME = ".snipcom-folder.json"
    COMMAND_FOLDER_KEY = "folder_path"

    def __init__(self, texts_dir: Path) -> None:
        self.set_texts_dir(texts_dir)

    def set_texts_dir(self, texts_dir: Path) -> None:
        self.texts_dir = texts_dir
        self.app_state_dir = self.texts_dir / ".snipcom"
        self.tags_file = self.app_state_dir / "tags.json"
        self.launch_options_file = self.app_state_dir / "launch-options.json"
        self.snip_types_file = self.app_state_dir / "snip-types.json"
        self.descriptions_file = self.app_state_dir / "descriptions.json"
        self.command_backups_dir = self.app_state_dir / COMMAND_BACKUPS_DIRNAME
        self.command_store = CommandStore(self.app_state_dir / "commands.sqlite3")
        self.user_command_store = UserCommandStore(self.app_state_dir / "my_commands.json")
        self.trash_dir = self.texts_dir / "Trash bin"

    def ensure_storage(self) -> None:
        self.texts_dir.mkdir(parents=True, exist_ok=True)
        self.app_state_dir.mkdir(parents=True, exist_ok=True)
        self.command_backups_dir.mkdir(parents=True, exist_ok=True)
        self.command_store.ensure_schema()
        self.trash_dir.mkdir(parents=True, exist_ok=True)

    def storage_key(self, path: Path) -> str:
        return path.relative_to(self.texts_dir).as_posix()

    def file_entry_id(self, path: Path) -> str:
        return f"file:{self.storage_key(path)}"

    def folder_entry_id(self, path: Path) -> str:
        return f"folder:{self.storage_key(path)}"

    def command_entry_id(self, command_id: int) -> str:
        return f"command:{command_id}"

    def entry_path(self, entry_id: str) -> Path | None:
        if not (entry_id.startswith("file:") or entry_id.startswith("folder:")):
            return None
        relative = entry_id.partition(":")[2]
        if not relative:
            return None
        return self.texts_dir / relative

    def parse_command_id(self, entry_id: str) -> int | None:
        if not entry_id.startswith("command:"):
            return None
        _, _, value = entry_id.partition(":")
        try:
            return int(value)
        except ValueError:
            return None

    def active_files(self) -> list[Path]:
        return [path for path in self.texts_dir.iterdir() if is_text_file(path)]

    def active_folders(self) -> list[Path]:
        return [
            path
            for path in self.texts_dir.iterdir()
            if path.is_dir()
            and path.name != self.trash_dir.name
            and path.name != self.app_state_dir.name
            and not path.name.startswith(".")
        ]

    def trash_files(self) -> list[Path]:
        return [path for path in self.trash_dir.iterdir() if is_text_file(path)]

    def trashed_command_entries(self) -> list[SnipcomEntry]:
        return [self.command_entry_from_record(record) for record in self.command_store.list_trashed_commands()]

    def trash_count(self) -> int:
        return len(self.trash_files()) + self.command_store.count_trashed_commands()

    def resolve_text_file_path(self, file_name: str, *, fallback_suffix: str | None = ".txt") -> Path:
        path = self.texts_dir / file_name
        if fallback_suffix and not path.suffix:
            path = path.with_suffix(fallback_suffix)
        return path

    def create_file(self, file_name: str, *, fallback_suffix: str | None = ".txt") -> Path:
        path = self.resolve_text_file_path(file_name, fallback_suffix=fallback_suffix)
        path.write_text("", encoding="utf-8")
        return path

    def folder_meta_path(self, folder_path: Path) -> Path:
        return folder_path / self.FOLDER_META_FILENAME

    def folder_mode(self, folder_path: Path) -> str:
        meta_path = self.folder_meta_path(folder_path)
        payload = read_json_file(meta_path)
        mode = str(payload.get("mode", "")).strip().casefold()
        if mode in {"popup", "normal"}:
            return mode
        return "normal"

    def set_folder_mode(self, folder_path: Path, mode: str) -> None:
        cleaned_mode = mode.strip().casefold()
        if cleaned_mode not in {"popup", "normal"}:
            cleaned_mode = "normal"
        payload = {"mode": cleaned_mode}
        self.folder_meta_path(folder_path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def create_folder(self, folder_name: str, *, mode: str) -> Path:
        folder_path = self.texts_dir / folder_name
        folder_path.mkdir()
        self.set_folder_mode(folder_path, mode)
        return folder_path

    def rename_folder(self, folder_path: Path, new_name: str) -> Path:
        new_path = self.texts_dir / new_name
        folder_path.rename(new_path)
        return new_path

    def folder_visible_children(self, folder_path: Path) -> list[Path]:
        children: list[Path] = []
        for child in folder_path.iterdir():
            if child.name.startswith("."):
                continue
            if child.name == self.FOLDER_META_FILENAME:
                continue
            children.append(child)
        children.sort(key=lambda item: (not item.is_dir(), item.name.casefold()))
        return children

    def rename_file(self, path: Path, new_name: str, *, fallback_suffix: str | None = None) -> Path:
        new_path = self.texts_dir / new_name
        effective_suffix = fallback_suffix if fallback_suffix is not None else (path.suffix or None)
        if effective_suffix and not new_path.suffix:
            new_path = new_path.with_suffix(effective_suffix)
        path.rename(new_path)
        return new_path

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    def active_entries(self, tags: dict[str, str], snip_types: dict[str, str]) -> list[SnipcomEntry]:
        entries: list[SnipcomEntry] = []
        for folder_path in self.active_folders():
            entries.append(self.folder_entry_from_path(folder_path))
        for path in self.active_files():
            snip_type = normalize_command_snip_type(snip_types.get(self.storage_key(path), "text_file"))
            if snip_type != "text_file":
                continue
            entries.append(self.file_entry_from_path(path, tags, snip_types))
        entries.extend(
            self.command_entry_from_record(record)
            for record in self.command_store.list_commands(catalog_only=False)
            if not self.command_folder_storage_key(record)
        )
        entries.extend(
            self.user_command_entry_from_dict(d)
            for d in self.user_command_store.list_all()
            if not d.get("folder_key", "")
        )
        return entries

    def folder_entries(self, folder_path: Path, tags: dict[str, str], snip_types: dict[str, str]) -> list[SnipcomEntry]:
        entries: list[SnipcomEntry] = []
        for child in self.folder_visible_children(folder_path):
            if child.is_dir():
                entries.append(self.folder_entry_from_path(child))
            else:
                entries.append(self.file_entry_from_path(child, tags, snip_types))
        folder_key = self.storage_key(folder_path)
        entries.extend(
            self.command_entry_from_record(record)
            for record in self.command_store.list_commands(catalog_only=False)
            if self.command_folder_storage_key(record) == folder_key
        )
        entries.extend(
            self.user_command_entry_from_dict(d)
            for d in self.user_command_store.list_all()
            if d.get("folder_key", "") == folder_key
        )
        return entries

    def command_folder_storage_key(self, record: CommandRecord) -> str:
        value = str(record.extra.get(self.COMMAND_FOLDER_KEY, "") or "").strip()
        return value

    def command_entries_in_folder(self, folder_path: Path) -> list[CommandRecord]:
        folder_key = self.storage_key(folder_path)
        return [
            record
            for record in self.command_store.list_commands(catalog_only=False)
            if self.command_folder_storage_key(record) == folder_key
        ]

    def set_command_folder(self, command_id: int, folder_path: Path | None) -> CommandRecord:
        record = self.command_store.get_command(command_id)
        extra = dict(record.extra)
        if folder_path is None:
            extra.pop(self.COMMAND_FOLDER_KEY, None)
        else:
            extra[self.COMMAND_FOLDER_KEY] = self.storage_key(folder_path)
        return self.command_store.update_command(command_id, extra=extra)

    def reassign_command_folder_prefix(self, old_folder_path: Path, new_folder_path: Path | None) -> None:
        old_prefix = self.storage_key(old_folder_path)
        old_prefix_with_sep = f"{old_prefix}/"
        new_prefix = self.storage_key(new_folder_path) if new_folder_path is not None else ""
        for record in self.command_store.list_commands(catalog_only=False):
            current = self.command_folder_storage_key(record)
            if not current:
                continue
            if current == old_prefix:
                updated = new_prefix
            elif current.startswith(old_prefix_with_sep):
                suffix = current[len(old_prefix_with_sep):]
                updated = f"{new_prefix}/{suffix}" if new_prefix else ""
            else:
                continue
            extra = dict(record.extra)
            if updated:
                extra[self.COMMAND_FOLDER_KEY] = updated
            else:
                extra.pop(self.COMMAND_FOLDER_KEY, None)
            self.command_store.update_command(record.command_id, extra=extra)
        for d in self.user_command_store.list_all():
            current = d.get("folder_key", "")
            if not current:
                continue
            if current == old_prefix:
                updated = new_prefix
            elif current.startswith(old_prefix_with_sep):
                suffix = current[len(old_prefix_with_sep):]
                updated = f"{new_prefix}/{suffix}" if new_prefix else ""
            else:
                continue
            self.user_command_store.set_folder(d["id"], updated)

    def catalog_entries(self, *, include_active_commands: bool = True) -> list[SnipcomEntry]:
        entries = [
            self.command_entry_from_record(record)
            for record in self.command_store.list_commands(catalog_only=True)
        ]
        if include_active_commands:
            entries.extend(
                self.command_entry_from_record(record)
                for record in self.command_store.list_commands(catalog_only=False)
            )
        return entries

    def entry_from_id(
        self,
        entry_id: str,
        tags: dict[str, str],
        snip_types: dict[str, str],
        *,
        include_trashed: bool = False,
    ) -> SnipcomEntry | None:
        path = self.entry_path(entry_id)
        if path is not None:
            if not path.exists():
                return None
            if path.is_dir():
                return self.folder_entry_from_path(path)
            return self.file_entry_from_path(path, tags, snip_types)

        if entry_id.startswith("json_command:"):
            uid = entry_id[len("json_command:"):]
            try:
                d = self.user_command_store.get(uid)
            except KeyError:
                return None
            return self.user_command_entry_from_dict(d)

        command_id = self.parse_command_id(entry_id)
        if command_id is None:
            return None
        try:
            record = self.command_store.get_command(command_id, include_trashed=include_trashed)
        except KeyError:
            return None
        if record.is_trashed and not include_trashed:
            return None
        return self.command_entry_from_record(record)

    def file_entry_from_path(
        self,
        path: Path,
        tags: dict[str, str],
        snip_types: dict[str, str],
    ) -> SnipcomEntry:
        stat = path.stat()
        storage_key = self.storage_key(path)
        snip_type = normalize_command_snip_type(snip_types.get(storage_key, "text_file"))
        if path.suffix.casefold() == ".txt":
            display_name = path.stem
        else:
            display_name = path.name
        return SnipcomEntry(
            entry_id=self.file_entry_id(path),
            backend="file",
            name=path.name,
            display_name=display_name,
            snip_type=snip_type,
            tag_text=tags.get(storage_key, ""),
            size_bytes=stat.st_size,
            modified_timestamp=stat.st_mtime,
            dangerous=False,
            family_key="",
            catalog_only=False,
            import_batch_id=0,
            source_kind="file",
            source_ref=storage_key,
            source_license="",
            path=path,
            command_id=None,
        )

    def folder_entry_from_path(self, path: Path) -> SnipcomEntry:
        stat = path.stat()
        child_count = len(self.folder_visible_children(path))
        mode = self.folder_mode(path)
        return SnipcomEntry(
            entry_id=self.folder_entry_id(path),
            backend="folder",
            name=path.name,
            display_name=path.name,
            snip_type="folder",
            tag_text="",
            size_bytes=child_count,
            modified_timestamp=stat.st_mtime,
            dangerous=False,
            family_key="",
            catalog_only=False,
            import_batch_id=0,
            source_kind="folder",
            source_ref=self.storage_key(path),
            source_license="",
            path=path,
            command_id=None,
            folder_mode=mode,
        )

    def command_entry_from_record(self, record: CommandRecord) -> SnipcomEntry:
        return SnipcomEntry(
            entry_id=self.command_entry_id(record.command_id),
            backend="command",
            name=record.title,
            display_name=record.title,
            snip_type=record.snip_type,
            tag_text=join_tags(record.tags),
            size_bytes=len(record.body.encode("utf-8")),
            modified_timestamp=self.iso_timestamp(record.updated_at),
            dangerous=record.dangerous,
            family_key=record.family_key,
            catalog_only=record.catalog_only,
            import_batch_id=record.import_batch_id,
            source_kind=record.source_kind,
            source_ref=record.source_ref,
            source_license=record.source_license,
            path=None,
            command_id=record.command_id,
            description=record.description,
            body=record.body,
        )

    def user_command_entry_from_dict(self, d: dict) -> SnipcomEntry:
        return SnipcomEntry(
            entry_id=f"json_command:{d['id']}",
            backend="json_command",
            name=d["title"],
            display_name=d["title"],
            snip_type="family_command",
            tag_text="",
            size_bytes=len(d["body"].encode("utf-8")),
            modified_timestamp=self.iso_timestamp(d.get("updated_at", "")),
            dangerous=False,
            family_key="",
            catalog_only=False,
            import_batch_id=0,
            source_kind="json_command",
            source_ref=d["id"],
            source_license="",
            path=None,
            command_id=None,
            description=d.get("description", ""),
            body=d["body"],
        )

    def set_json_command_folder(self, uid: str, folder_path: Path | None) -> None:
        folder_key = self.storage_key(folder_path) if folder_path is not None else ""
        self.user_command_store.set_folder(uid, folder_key)

    def create_user_command(self, title: str, body: str, description: str = "") -> SnipcomEntry:
        d = self.user_command_store.create(title, body, description)
        return self.user_command_entry_from_dict(d)

    def iso_timestamp(self, value: str) -> float:
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0

    def trash_snapshot(self, tags: dict[str, str], snip_types: dict[str, str], files: list[Path]) -> list[dict]:
        snapshot: list[dict] = []
        for path in files:
            content = path.read_bytes()
            key = self.storage_key(path)
            snapshot.append(
                {
                    "name": path.name,
                    "content": content,
                    "tag": tags.get(key, ""),
            "snip_type": normalize_command_snip_type(snip_types.get(key, "text_file")),
                }
            )
        return snapshot

    def command_snapshot(self, command_id: int) -> dict[str, object]:
        record = self.command_store.get_command(command_id, include_trashed=True)
        return {
            "title": record.title,
            "body": record.body,
            "snip_type": record.snip_type,
            "family_key": record.family_key,
            "description": record.description,
            "source_kind": record.source_kind,
            "source_ref": record.source_ref,
            "source_license": record.source_license,
            "import_batch_id": record.import_batch_id,
            "catalog_only": record.catalog_only,
            "dangerous": record.dangerous,
            "launch_options": dict(record.launch_options),
            "tags": list(record.tags),
            "extra": dict(record.extra),
        }

    def restore_command_snapshot(self, snapshot: dict[str, object]) -> SnipcomEntry:
        title = str(snapshot.get("title", "")).strip()
        if not title:
            title = "Restored command"
        title = self.unique_command_title(title)
        record = self.command_store.create_command(
            title,
            body=str(snapshot.get("body", "")),
            snip_type=normalize_command_snip_type(str(snapshot.get("snip_type", "family_command"))),
            family_key=str(snapshot.get("family_key", "")),
            description=str(snapshot.get("description", "")),
            source_kind=str(snapshot.get("source_kind", "local")),
            source_ref=str(snapshot.get("source_ref", "")),
            source_license=str(snapshot.get("source_license", "")),
            import_batch_id=int(snapshot.get("import_batch_id", 0) or 0),
            catalog_only=bool(snapshot.get("catalog_only", False)),
            dangerous=bool(snapshot.get("dangerous", False)),
            launch_options=normalize_launch_options(snapshot.get("launch_options")),
            tags=[str(tag) for tag in snapshot.get("tags", [])],
            extra=snapshot.get("extra") if isinstance(snapshot.get("extra"), dict) else {},
        )
        return self.command_entry_from_record(record)

    def create_import_batch(
        self,
        *,
        label: str,
        source_kind: str,
        source_ref: str = "",
        source_license: str = "",
        summary: dict[str, object] | None = None,
    ) -> int:
        return self.command_store.create_import_batch(
            label=label,
            source_kind=source_kind,
            source_ref=source_ref,
            source_license=source_license,
            summary=summary,
        )

    def list_import_batches(self) -> list[dict[str, object]]:
        return self.command_store.list_import_batches()

    def upsert_import_source(
        self,
        *,
        name: str,
        kind: str,
        path_or_url: str,
        is_git: bool = False,
        local_checkout_path: str = "",
    ) -> ImportSourceRecord:
        return self.command_store.upsert_import_source(
            name=name,
            kind=kind,
            path_or_url=path_or_url,
            is_git=is_git,
            local_checkout_path=local_checkout_path,
        )

    def list_import_sources(self) -> list[ImportSourceRecord]:
        return self.command_store.list_import_sources()

    def get_import_source(self, source_id: int) -> ImportSourceRecord:
        return self.command_store.get_import_source(source_id)

    def get_import_source_by_name(self, name: str) -> ImportSourceRecord:
        return self.command_store.get_import_source_by_name(name)

    def delete_import_source(self, source_id: int) -> None:
        self.command_store.delete_import_source(source_id)

    def update_import_source(
        self,
        source_id: int,
        *,
        local_checkout_path: str | None = None,
        last_sync_at: str | None = None,
        last_status: str | None = None,
        last_batch_id: int | None = None,
    ) -> ImportSourceRecord:
        return self.command_store.update_import_source(
            source_id,
            local_checkout_path=local_checkout_path,
            last_sync_at=last_sync_at,
            last_status=last_status,
            last_batch_id=last_batch_id,
        )

    def find_catalog_command_by_source_key(self, source_key: str) -> SnipcomEntry | None:
        record = self.command_store.find_catalog_command_by_source_key(source_key)
        if record is None:
            return None
        return self.command_entry_from_record(record)

    def clone_command_to_workflow(self, command_id: int, target_snip_type: str) -> SnipcomEntry:
        record = self.command_store.get_command(command_id)
        if target_snip_type == "text_file":
            file_name = available_path(self.texts_dir, f"{self.safe_text_file_name(record.title)}.txt").name
            path = self.create_file(file_name, fallback_suffix=".txt")
            self.write_text(path, record.body)
            return SnipcomEntry(
                entry_id=self.file_entry_id(path),
                backend="file",
                name=path.name,
                display_name=path.stem if path.suffix.casefold() == ".txt" else path.name,
                snip_type="text_file",
                tag_text=join_tags(record.tags),
                size_bytes=path.stat().st_size,
                modified_timestamp=path.stat().st_mtime,
                dangerous=False,
                family_key="",
                catalog_only=False,
                import_batch_id=0,
                source_kind="file",
                source_ref=self.storage_key(path),
                source_license="",
                path=path,
                command_id=None,
            )

        cloned_record = self.command_store.create_command(
            self.unique_workflow_clone_title(
                record.title,
                normalize_command_snip_type(target_snip_type) if normalize_command_snip_type(target_snip_type) == "family_command" else record.snip_type,
            ),
            body=record.body,
            snip_type=normalize_command_snip_type(target_snip_type) if normalize_command_snip_type(target_snip_type) == "family_command" else record.snip_type,
            family_key=record.family_key,
            description=record.description,
            source_kind=record.source_kind or "catalog-clone",
            source_ref=record.source_ref,
            source_license=record.source_license,
            dangerous=record.dangerous,
            launch_options=dict(record.launch_options),
            tags=list(record.tags),
            extra=dict(record.extra),
        )
        return self.command_entry_from_record(cloned_record)

    def safe_text_file_name(self, desired_name: str) -> str:
        cleaned = desired_name.strip().replace("/", " - ").replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip(" .")
        return cleaned[:120] or "command"

    def empty_trash(
        self,
        files: list[Path],
        tags: dict[str, str],
        snip_types: dict[str, str],
        launch_options: dict[str, dict[str, object]],
    ) -> list[dict]:
        snapshot = self.trash_snapshot(tags, snip_types, files)
        for path in files:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            self.remove_metadata(tags, snip_types, launch_options, path)
        return snapshot

    def delete_trashed_commands(self) -> list[dict[str, object]]:
        snapshots: list[dict[str, object]] = []
        for record in self.command_store.list_trashed_commands():
            snapshots.append(self.command_snapshot(record.command_id))
            self.command_store.delete_command(record.command_id)
        return snapshots

    def restore_trash_snapshot(self, snapshot: list[dict]) -> int:
        restored = 0
        for file_data in snapshot:
            path = available_path(self.trash_dir, file_data["name"])
            path.write_bytes(file_data["content"])
            restored += 1
        return restored

    def restore_paths_from_trash(
        self,
        paths: list[Path],
        tags: dict[str, str],
        snip_types: dict[str, str],
        launch_options: dict[str, dict[str, object]],
    ) -> list[tuple[Path, Path]]:
        restored_paths: list[tuple[Path, Path]] = []
        for path in paths:
            if not path.exists():
                continue
            restored_path = available_path(self.texts_dir, path.name)
            path.rename(restored_path)
            self.move_metadata(tags, snip_types, launch_options, path, restored_path)
            restored_paths.append((path, restored_path))
        return restored_paths

    def move_paths_to_trash(
        self,
        paths: list[Path],
        tags: dict[str, str],
        snip_types: dict[str, str],
        launch_options: dict[str, dict[str, object]],
    ) -> list[tuple[Path, Path]]:
        moved_paths: list[tuple[Path, Path]] = []
        for path in paths:
            if not path.exists():
                continue
            trashed_path = available_path(self.trash_dir, path.name)
            path.rename(trashed_path)
            self.move_metadata(tags, snip_types, launch_options, path, trashed_path)
            moved_paths.append((path, trashed_path))
        return moved_paths

    def move_file_to_command_backup(self, path: Path) -> Path:
        self.command_backups_dir.mkdir(parents=True, exist_ok=True)
        backup_path = available_path(self.command_backups_dir, path.name)
        path.rename(backup_path)
        return backup_path

    def unique_command_title(self, desired_title: str, *, exclude_id: int | None = None) -> str:
        cleaned_title = desired_title.strip() or "command"
        if not self.command_store.title_exists(cleaned_title, exclude_id=exclude_id):
            return cleaned_title

        index = 2
        while True:
            candidate = f"{cleaned_title} {index}"
            if not self.command_store.title_exists(candidate, exclude_id=exclude_id):
                return candidate
            index += 1

    def workflow_command_title_exists(self, title: str, *, exclude_id: int | None = None) -> bool:
        cleaned_title = title.strip()
        if not cleaned_title:
            return False
        for record in self.command_store.list_commands(catalog_only=False):
            if exclude_id is not None and record.command_id == exclude_id:
                continue
            if record.title.casefold() == cleaned_title.casefold():
                return True
        return False

    def unique_workflow_clone_title(self, desired_title: str, snip_type: str) -> str:
        cleaned_title = desired_title.strip() or "command"
        if not self.workflow_command_title_exists(cleaned_title):
            return cleaned_title

        suffix_prefix = "fam"
        index = 1
        while True:
            candidate = f"{cleaned_title} - {suffix_prefix}{index}"
            if not self.workflow_command_title_exists(candidate):
                return candidate
            index += 1
