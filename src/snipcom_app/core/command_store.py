from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .command_store_models import CommandRecord, ImportSourceRecord, normalize_command_snip_type
from .command_store_usage import CommandUsageMixin
from .helpers import join_tags, normalize_launch_options, slugify_casefold, split_tags, utc_now_iso


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL DEFAULT '',
    source_license TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS import_sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    path_or_url TEXT NOT NULL,
    is_git INTEGER NOT NULL DEFAULT 0,
    local_checkout_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_sync_at TEXT NOT NULL DEFAULT '',
    last_status TEXT NOT NULL DEFAULT '',
    last_batch_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    snip_type TEXT NOT NULL CHECK (snip_type IN ('family_command')),
    family_key TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT 'local',
    source_ref TEXT NOT NULL DEFAULT '',
    source_license TEXT NOT NULL DEFAULT '',
    import_batch_id INTEGER NOT NULL DEFAULT 0,
    catalog_only INTEGER NOT NULL DEFAULT 0,
    dangerous INTEGER NOT NULL DEFAULT 0,
    launch_options_json TEXT NOT NULL DEFAULT '{}',
    trashed_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    extra_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS command_tags (
    command_id INTEGER NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (command_id, tag)
);

CREATE TABLE IF NOT EXISTS command_usage (
    id INTEGER PRIMARY KEY,
    command_id INTEGER NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
    terminal_label TEXT NOT NULL DEFAULT '',
    event_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS command_transitions (
    from_command_id INTEGER NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
    to_command_id INTEGER NOT NULL REFERENCES commands(id) ON DELETE CASCADE,
    terminal_label TEXT NOT NULL DEFAULT '',
    weight INTEGER NOT NULL DEFAULT 1,
    last_used_at TEXT NOT NULL,
    PRIMARY KEY (from_command_id, to_command_id, terminal_label)
);

CREATE VIRTUAL TABLE IF NOT EXISTS commands_fts USING fts5(
    title,
    body,
    family_key,
    description,
    content='commands',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS commands_ai AFTER INSERT ON commands BEGIN
    INSERT INTO commands_fts(rowid, title, body, family_key, description)
    VALUES (new.id, new.title, new.body, new.family_key, new.description);
END;

CREATE TRIGGER IF NOT EXISTS commands_ad AFTER DELETE ON commands BEGIN
    INSERT INTO commands_fts(commands_fts, rowid, title, body, family_key, description)
    VALUES('delete', old.id, old.title, old.body, old.family_key, old.description);
END;

CREATE TRIGGER IF NOT EXISTS commands_au AFTER UPDATE ON commands BEGIN
    INSERT INTO commands_fts(commands_fts, rowid, title, body, family_key, description)
    VALUES('delete', old.id, old.title, old.body, old.family_key, old.description);
    INSERT INTO commands_fts(rowid, title, body, family_key, description)
    VALUES (new.id, new.title, new.body, new.family_key, new.description);
END;
"""


class CommandStore(CommandUsageMixin):
    def __init__(self, database_path: Path) -> None:
        self.set_database_path(database_path)

    def set_database_path(self, database_path: Path) -> None:
        self.database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "commands", "source_license", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "commands", "import_batch_id", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "commands", "catalog_only", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "commands", "dangerous", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "commands", "launch_options_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(connection, "commands", "trashed_at", "TEXT NOT NULL DEFAULT ''")
            connection.execute("INSERT INTO commands_fts(commands_fts) VALUES('rebuild')")
            connection.commit()
        finally:
            connection.close()

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column in columns:
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def create_import_batch(
        self,
        *,
        label: str,
        source_kind: str,
        source_ref: str = "",
        source_license: str = "",
        summary: dict[str, object] | None = None,
    ) -> int:
        connection = self.connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO import_batches(label, source_kind, source_ref, source_license, created_at, summary_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    label.strip() or "Imported batch",
                    source_kind.strip() or "import",
                    source_ref.strip(),
                    source_license.strip(),
                    utc_now_iso(),
                    json.dumps(summary or {}, sort_keys=True),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def upsert_import_source(
        self,
        *,
        name: str,
        kind: str,
        path_or_url: str,
        is_git: bool = False,
        local_checkout_path: str = "",
    ) -> ImportSourceRecord:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Import source name cannot be empty.")
        cleaned_kind = kind.strip()
        if not cleaned_kind:
            raise ValueError("Import source kind cannot be empty.")
        cleaned_path = path_or_url.strip()
        if not cleaned_path:
            raise ValueError("Import source path or URL cannot be empty.")
        now = utc_now_iso()

        connection = self.connect()
        try:
            existing = connection.execute(
                "SELECT * FROM import_sources WHERE lower(name) = lower(?) LIMIT 1",
                (cleaned_name,),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO import_sources(
                        name, kind, path_or_url, is_git, local_checkout_path,
                        created_at, updated_at, last_sync_at, last_status, last_batch_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, '', '', 0)
                    """,
                    (
                        cleaned_name,
                        cleaned_kind,
                        cleaned_path,
                        1 if is_git else 0,
                        local_checkout_path.strip(),
                        now,
                        now,
                    ),
                )
                source_id = int(cursor.lastrowid)
            else:
                source_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE import_sources
                    SET kind = ?, path_or_url = ?, is_git = ?, local_checkout_path = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        cleaned_kind,
                        cleaned_path,
                        1 if is_git else 0,
                        local_checkout_path.strip(),
                        now,
                        source_id,
                    ),
                )
            connection.commit()
        finally:
            connection.close()
        return self.get_import_source(source_id)

    def list_import_sources(self) -> list[ImportSourceRecord]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM import_sources
                ORDER BY lower(name), id
                """
            ).fetchall()
        finally:
            connection.close()
        return [self._import_source_from_row(row) for row in rows]

    def get_import_source(self, source_id: int) -> ImportSourceRecord:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE id = ? LIMIT 1",
                (int(source_id),),
            ).fetchone()
            if row is None:
                raise KeyError(source_id)
            return self._import_source_from_row(row)
        finally:
            connection.close()

    def get_import_source_by_name(self, name: str) -> ImportSourceRecord:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM import_sources WHERE lower(name) = lower(?) LIMIT 1",
                (name.strip(),),
            ).fetchone()
            if row is None:
                raise KeyError(name)
            return self._import_source_from_row(row)
        finally:
            connection.close()

    def update_import_source(
        self,
        source_id: int,
        *,
        local_checkout_path: str | None = None,
        last_sync_at: str | None = None,
        last_status: str | None = None,
        last_batch_id: int | None = None,
    ) -> ImportSourceRecord:
        updates: list[str] = []
        values: list[object] = []
        if local_checkout_path is not None:
            updates.append("local_checkout_path = ?")
            values.append(local_checkout_path.strip())
        if last_sync_at is not None:
            updates.append("last_sync_at = ?")
            values.append(last_sync_at.strip())
        if last_status is not None:
            updates.append("last_status = ?")
            values.append(last_status.strip())
        if last_batch_id is not None:
            updates.append("last_batch_id = ?")
            values.append(int(last_batch_id))
        updates.append("updated_at = ?")
        values.append(utc_now_iso())
        values.append(int(source_id))

        connection = self.connect()
        try:
            connection.execute(
                f"UPDATE import_sources SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            connection.commit()
        finally:
            connection.close()
        return self.get_import_source(source_id)

    def list_import_batches(self) -> list[dict[str, object]]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT id, label, source_kind, source_ref, source_license, created_at, summary_json
                FROM import_batches
                ORDER BY id DESC
                """
            ).fetchall()
        finally:
            connection.close()

        batches: list[dict[str, object]] = []
        for row in rows:
            try:
                summary = json.loads(str(row["summary_json"] or "{}"))
            except json.JSONDecodeError:
                summary = {}
            if not isinstance(summary, dict):
                summary = {}
            batches.append(
                {
                    "id": int(row["id"]),
                    "label": str(row["label"]),
                    "source_kind": str(row["source_kind"]),
                    "source_ref": str(row["source_ref"] or ""),
                    "source_license": str(row["source_license"] or ""),
                    "created_at": str(row["created_at"]),
                    "summary": summary,
                }
            )
        return batches

    def delete_import_batch(self, batch_id: int) -> None:
        connection = self.connect()
        try:
            connection.execute("DELETE FROM import_batches WHERE id = ?", (int(batch_id),))
            connection.commit()
        finally:
            connection.close()

    def delete_import_source(self, source_id: int) -> None:
        connection = self.connect()
        try:
            connection.execute("DELETE FROM import_sources WHERE id = ?", (int(source_id),))
            connection.commit()
        finally:
            connection.close()

    def create_command(
        self,
        title: str,
        *,
        body: str = "",
        snip_type: str = "family_command",
        family_key: str = "",
        description: str = "",
        source_kind: str = "local",
        source_ref: str = "",
        source_license: str = "",
        import_batch_id: int = 0,
        catalog_only: bool = False,
        dangerous: bool = False,
        launch_options: dict[str, object] | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        extra: dict[str, object] | None = None,
    ) -> CommandRecord:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Command title cannot be empty.")
        snip_type = normalize_command_snip_type(snip_type)
        if snip_type != "family_command":
            raise ValueError("Invalid command snipType.")

        normalized_tags = split_tags(join_tags(tags or []))
        now = utc_now_iso()
        connection = self.connect()
        try:
            slug = self._unique_slug(connection, cleaned_title)
            cursor = connection.execute(
                """
                INSERT INTO commands (
                    slug,
                    title,
                    body,
                    snip_type,
                    family_key,
                    description,
                    source_kind,
                    source_ref,
                    source_license,
                    import_batch_id,
                    catalog_only,
                    dangerous,
                    launch_options_json,
                    trashed_at,
                    created_at,
                    updated_at,
                    extra_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
                """,
                (
                    slug,
                    cleaned_title,
                    body,
                    snip_type,
                    family_key.strip(),
                    description.strip(),
                    source_kind.strip() or "local",
                    source_ref.strip(),
                    source_license.strip(),
                    int(import_batch_id),
                    1 if catalog_only else 0,
                    1 if dangerous else 0,
                    json.dumps(normalize_launch_options(launch_options)),
                    now,
                    now,
                    json.dumps(extra or {}, sort_keys=True),
                ),
            )
            command_id = int(cursor.lastrowid)
            self._replace_tags(connection, command_id, normalized_tags)
            connection.commit()
            return self.get_command(command_id)
        finally:
            connection.close()

    def list_commands(
        self,
        *,
        include_trashed: bool = False,
        catalog_only: bool | None = None,
        import_batch_id: int | None = None,
    ) -> list[CommandRecord]:
        connection = self.connect()
        try:
            conditions = ["(? = 1 OR c.trashed_at = '')"]
            parameters: list[object] = [1 if include_trashed else 0]
            if catalog_only is not None:
                conditions.append("c.catalog_only = ?")
                parameters.append(1 if catalog_only else 0)
            if import_batch_id is not None:
                conditions.append("c.import_batch_id = ?")
                parameters.append(int(import_batch_id))

            rows = connection.execute(
                """
                SELECT
                    c.*,
                    COALESCE(GROUP_CONCAT(t.tag, ', '), '') AS tag_text
                FROM commands AS c
                LEFT JOIN command_tags AS t ON t.command_id = c.id
                WHERE """ + " AND ".join(conditions) + """
                GROUP BY c.id
                ORDER BY lower(c.title), c.id
                """,
                parameters,
            ).fetchall()
            return [self._record_from_row(row) for row in rows]
        finally:
            connection.close()

    def list_trashed_commands(self) -> list[CommandRecord]:
        return [record for record in self.list_commands(include_trashed=True) if record.is_trashed]

    def search_commands_fts(
        self,
        query: str,
        *,
        catalog_only: bool | None = None,
        limit: int = 60,
    ) -> list[CommandRecord]:
        """Search commands via FTS5 MATCH for fast prefix full-text search.

        Tokens are sanitized and suffixed with '*' for prefix matching.
        Returns an empty list if the query is blank or FTS fails.
        """
        tokens = [re.sub(r"[^\w\-]", "", tok, flags=re.UNICODE) for tok in query.strip().split()]
        tokens = [t for t in tokens if t]
        if not tokens:
            return []
        fts_query = " ".join(t + "*" for t in tokens)
        conditions = ["c.trashed_at = ''"]
        parameters: list[object] = [fts_query]
        if catalog_only is not None:
            conditions.append("c.catalog_only = ?")
            parameters.append(1 if catalog_only else 0)
        parameters.append(limit)
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    c.*,
                    COALESCE(GROUP_CONCAT(t.tag, ', '), '') AS tag_text
                FROM commands AS c
                LEFT JOIN command_tags AS t ON t.command_id = c.id
                WHERE c.id IN (SELECT rowid FROM commands_fts WHERE commands_fts MATCH ?)
                AND """ + " AND ".join(conditions) + """
                GROUP BY c.id
                ORDER BY lower(c.title), c.id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            return [self._record_from_row(row) for row in rows]
        except Exception:
            return []
        finally:
            connection.close()

    def get_command(self, command_id: int, *, include_trashed: bool = True) -> CommandRecord:
        connection = self.connect()
        try:
            row = connection.execute(
                """
                SELECT
                    c.*,
                    COALESCE(GROUP_CONCAT(t.tag, ', '), '') AS tag_text
                FROM commands AS c
                LEFT JOIN command_tags AS t ON t.command_id = c.id
                WHERE c.id = ? AND (? = 1 OR c.trashed_at = '')
                GROUP BY c.id
                """,
                (command_id, 1 if include_trashed else 0),
            ).fetchone()
            if row is None:
                raise KeyError(command_id)
            return self._record_from_row(row)
        finally:
            connection.close()

    def update_command(
        self,
        command_id: int,
        *,
        title: str | None = None,
        body: str | None = None,
        snip_type: str | None = None,
        family_key: str | None = None,
        description: str | None = None,
        source_kind: str | None = None,
        source_ref: str | None = None,
        source_license: str | None = None,
        import_batch_id: int | None = None,
        catalog_only: bool | None = None,
        dangerous: bool | None = None,
        launch_options: dict[str, object] | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        extra: dict[str, object] | None = None,
    ) -> CommandRecord:
        updates: list[str] = []
        parameters: list[object] = []

        connection = self.connect()
        try:
            if title is not None:
                cleaned_title = title.strip()
                if not cleaned_title:
                    raise ValueError("Command title cannot be empty.")
                updates.extend(["title = ?", "slug = ?"])
                parameters.extend([cleaned_title, self._unique_slug(connection, cleaned_title, exclude_id=command_id)])
            if body is not None:
                updates.append("body = ?")
                parameters.append(body)
            if snip_type is not None:
                snip_type = normalize_command_snip_type(snip_type)
                if snip_type != "family_command":
                    raise ValueError("Invalid command snipType.")
                updates.append("snip_type = ?")
                parameters.append(snip_type)
            if family_key is not None:
                updates.append("family_key = ?")
                parameters.append(family_key.strip())
            if description is not None:
                updates.append("description = ?")
                parameters.append(description.strip())
            if source_kind is not None:
                updates.append("source_kind = ?")
                parameters.append(source_kind.strip())
            if source_ref is not None:
                updates.append("source_ref = ?")
                parameters.append(source_ref.strip())
            if source_license is not None:
                updates.append("source_license = ?")
                parameters.append(source_license.strip())
            if import_batch_id is not None:
                updates.append("import_batch_id = ?")
                parameters.append(int(import_batch_id))
            if catalog_only is not None:
                updates.append("catalog_only = ?")
                parameters.append(1 if catalog_only else 0)
            if dangerous is not None:
                updates.append("dangerous = ?")
                parameters.append(1 if dangerous else 0)
            if launch_options is not None:
                updates.append("launch_options_json = ?")
                parameters.append(json.dumps(normalize_launch_options(launch_options)))
            if extra is not None:
                updates.append("extra_json = ?")
                parameters.append(json.dumps(extra, sort_keys=True))

            if updates:
                updates.append("updated_at = ?")
                parameters.append(utc_now_iso())
                parameters.append(command_id)
                connection.execute(
                    f"UPDATE commands SET {', '.join(updates)} WHERE id = ?",
                    parameters,
                )

            if tags is not None:
                self._replace_tags(connection, command_id, split_tags(join_tags(tags)))

            connection.commit()
            return self.get_command(command_id, include_trashed=True)
        finally:
            connection.close()

    def move_command_to_trash(self, command_id: int) -> CommandRecord:
        connection = self.connect()
        try:
            now = utc_now_iso()
            connection.execute(
                "UPDATE commands SET trashed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, command_id),
            )
            connection.commit()
        finally:
            connection.close()
        return self.get_command(command_id, include_trashed=True)

    def restore_command_from_trash(self, command_id: int) -> CommandRecord:
        connection = self.connect()
        try:
            now = utc_now_iso()
            connection.execute(
                "UPDATE commands SET trashed_at = '', updated_at = ? WHERE id = ?",
                (now, command_id),
            )
            connection.commit()
        finally:
            connection.close()
        return self.get_command(command_id)

    def delete_command(self, command_id: int) -> None:
        connection = self.connect()
        try:
            connection.execute("DELETE FROM commands WHERE id = ?", (command_id,))
            connection.commit()
        finally:
            connection.close()

    def count_trashed_commands(self) -> int:
        connection = self.connect()
        try:
            row = connection.execute("SELECT COUNT(*) AS total FROM commands WHERE trashed_at <> ''").fetchone()
            return int(row["total"]) if row is not None else 0
        finally:
            connection.close()

    def title_exists(self, title: str, *, exclude_id: int | None = None) -> bool:
        cleaned_title = title.strip()
        if not cleaned_title:
            return False
        connection = self.connect()
        try:
            if exclude_id is None:
                row = connection.execute(
                    "SELECT 1 FROM commands WHERE lower(title) = lower(?) AND trashed_at = '' LIMIT 1",
                    (cleaned_title,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM commands
                    WHERE lower(title) = lower(?) AND id <> ? AND trashed_at = ''
                    LIMIT 1
                    """,
                    (cleaned_title, exclude_id),
                ).fetchone()
            return row is not None
        finally:
            connection.close()

    def _replace_tags(self, connection: sqlite3.Connection, command_id: int, tags: list[str]) -> None:
        connection.execute("DELETE FROM command_tags WHERE command_id = ?", (command_id,))
        for tag in tags:
            connection.execute(
                "INSERT OR IGNORE INTO command_tags(command_id, tag) VALUES (?, ?)",
                (command_id, tag),
            )

    def _unique_slug(self, connection: sqlite3.Connection, title: str, exclude_id: int | None = None) -> str:
        base = self._slugify(title) or "command"
        slug = base
        suffix = 2
        while self._slug_exists(connection, slug, exclude_id=exclude_id):
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    def _slug_exists(self, connection: sqlite3.Connection, slug: str, exclude_id: int | None = None) -> bool:
        if exclude_id is None:
            row = connection.execute("SELECT 1 FROM commands WHERE slug = ? LIMIT 1", (slug,)).fetchone()
        else:
            row = connection.execute(
                "SELECT 1 FROM commands WHERE slug = ? AND id <> ? LIMIT 1",
                (slug, exclude_id),
            ).fetchone()
        return row is not None

    def _slugify(self, text: str) -> str:
        return slugify_casefold(text)

    def _record_from_row(self, row: sqlite3.Row) -> CommandRecord:
        tag_text = str(row["tag_text"] or "")
        try:
            launch_options = json.loads(str(row["launch_options_json"] or "{}"))
        except json.JSONDecodeError:
            launch_options = {}
        try:
            extra = json.loads(str(row["extra_json"] or "{}"))
        except json.JSONDecodeError:
            extra = {}
        if not isinstance(launch_options, dict):
            launch_options = {}
        if not isinstance(extra, dict):
            extra = {}
        return CommandRecord(
            command_id=int(row["id"]),
            slug=str(row["slug"]),
            title=str(row["title"]),
            body=str(row["body"]),
            snip_type=normalize_command_snip_type(str(row["snip_type"])),
            family_key=str(row["family_key"] or ""),
            description=str(row["description"] or ""),
            source_kind=str(row["source_kind"] or "local"),
            source_ref=str(row["source_ref"] or ""),
            source_license=str(row["source_license"] or ""),
            import_batch_id=int(row["import_batch_id"] or 0),
            catalog_only=bool(row["catalog_only"]),
            dangerous=bool(row["dangerous"]),
            launch_options=normalize_launch_options(launch_options),
            trashed_at=str(row["trashed_at"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            extra=extra,
            tags=tuple(split_tags(tag_text)),
        )

    def _import_source_from_row(self, row: sqlite3.Row) -> ImportSourceRecord:
        return ImportSourceRecord(
            source_id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            path_or_url=str(row["path_or_url"]),
            is_git=bool(row["is_git"]),
            local_checkout_path=str(row["local_checkout_path"] or ""),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_sync_at=str(row["last_sync_at"] or ""),
            last_status=str(row["last_status"] or ""),
            last_batch_id=int(row["last_batch_id"] or 0),
        )
