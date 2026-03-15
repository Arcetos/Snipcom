from __future__ import annotations

import json
import sqlite3

from .command_store_models import CommandRecord
from .helpers import utc_now_iso


class CommandUsageMixin:
    """Mixin providing usage tracking and transition weight methods for CommandStore.

    Requires the host class to provide:
        self.connect() -> sqlite3.Connection
        self.get_command(command_id, *, include_trashed) -> CommandRecord
        self.list_commands(**kwargs) -> list[CommandRecord]
        self.transition_weights(from_command_id, *, terminal_label) -> dict[int, int]
        self.usage_counts() -> dict[int, int]
    """

    def record_usage(
        self,
        command_id: int,
        *,
        event_kind: str,
        terminal_label: str = "",
        context: dict[str, object] | None = None,
        track_transition: bool = False,
    ) -> None:
        connection = self.connect()
        try:
            now = utc_now_iso()
            previous_command_id: int | None = None
            cleaned_terminal_label = terminal_label.strip()
            cleaned_terminal_runtime = ""
            if isinstance(context, dict):
                cleaned_terminal_runtime = str(context.get("runtime_dir", "")).strip()
            if track_transition and cleaned_terminal_label:
                previous_command_id = self.latest_terminal_command_id(
                    cleaned_terminal_label,
                    include_event_kinds=("send", "launch", "terminal-input"),
                    terminal_runtime=cleaned_terminal_runtime,
                    connection=connection,
                )

            connection.execute(
                """
                INSERT INTO command_usage(command_id, terminal_label, event_kind, created_at, context_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    cleaned_terminal_label,
                    event_kind.strip() or "use",
                    now,
                    json.dumps(context or {}, sort_keys=True),
                ),
            )
            if track_transition and previous_command_id is not None and previous_command_id != command_id:
                connection.execute(
                    """
                    INSERT INTO command_transitions(from_command_id, to_command_id, terminal_label, weight, last_used_at)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(from_command_id, to_command_id, terminal_label)
                    DO UPDATE SET
                        weight = weight + 1,
                        last_used_at = excluded.last_used_at
                    """,
                    (previous_command_id, command_id, cleaned_terminal_label, now),
                )
            connection.commit()
        finally:
            connection.close()

    def usage_counts(self) -> dict[int, int]:
        connection = self.connect()
        try:
            rows = connection.execute(
                """
                SELECT command_id, COUNT(*) AS total
                FROM command_usage
                GROUP BY command_id
                """
            ).fetchall()
            return {int(row["command_id"]): int(row["total"]) for row in rows}
        finally:
            connection.close()

    def latest_terminal_command_id(
        self,
        terminal_label: str,
        *,
        include_event_kinds: tuple[str, ...] = ("send", "launch", "terminal-input"),
        terminal_runtime: str = "",
        connection: sqlite3.Connection | None = None,
    ) -> int | None:
        cleaned_terminal_label = terminal_label.strip()
        cleaned_terminal_runtime = terminal_runtime.strip()
        if not cleaned_terminal_label and not cleaned_terminal_runtime:
            return None
        owns_connection = connection is None
        connection = connection or self.connect()
        try:
            placeholders = ", ".join("?" for _ in include_event_kinds)
            if cleaned_terminal_runtime:
                runtime_json_fragment = json.dumps(cleaned_terminal_runtime)
                row = connection.execute(
                    f"""
                    SELECT u.command_id
                    FROM command_usage AS u
                    JOIN commands AS c ON c.id = u.command_id
                    WHERE u.event_kind IN ({placeholders})
                      AND c.trashed_at = ''
                      AND u.context_json LIKE ?
                    ORDER BY u.id DESC
                    LIMIT 1
                    """,
                    (*include_event_kinds, f'%"runtime_dir": {runtime_json_fragment}%'),
                ).fetchone()
            else:
                row = connection.execute(
                    f"""
                    SELECT u.command_id
                    FROM command_usage AS u
                    JOIN commands AS c ON c.id = u.command_id
                    WHERE u.terminal_label = ? AND u.event_kind IN ({placeholders}) AND c.trashed_at = ''
                    ORDER BY u.id DESC
                    LIMIT 1
                    """,
                    (cleaned_terminal_label, *include_event_kinds),
                ).fetchone()
            return int(row["command_id"]) if row is not None else None
        finally:
            if owns_connection:
                connection.close()

    def transition_weights(
        self,
        from_command_id: int,
        *,
        terminal_label: str = "",
    ) -> dict[int, int]:
        connection = self.connect()
        try:
            if terminal_label.strip():
                rows = connection.execute(
                    """
                    SELECT to_command_id, weight
                    FROM command_transitions
                    WHERE from_command_id = ? AND terminal_label = ?
                    ORDER BY weight DESC, to_command_id
                    """,
                    (from_command_id, terminal_label.strip()),
                ).fetchall()
                if rows:
                    return {int(row["to_command_id"]): int(row["weight"]) for row in rows}

            rows = connection.execute(
                """
                SELECT to_command_id, SUM(weight) AS total
                FROM command_transitions
                WHERE from_command_id = ?
                GROUP BY to_command_id
                ORDER BY total DESC, to_command_id
                """,
                (from_command_id,),
            ).fetchall()
            return {int(row["to_command_id"]): int(row["total"]) for row in rows}
        finally:
            connection.close()

    def related_command_ids(self, command_id: int, *, limit: int = 8) -> list[int]:
        try:
            record = self.get_command(command_id, include_trashed=False)
        except KeyError:
            return []
        transition_map = self.transition_weights(command_id)
        usage_map = self.usage_counts()
        candidate_scores: dict[int, int] = {}
        for target_id, weight in transition_map.items():
            candidate_scores[target_id] = candidate_scores.get(target_id, 0) + weight * 10
        for candidate in self.list_commands(catalog_only=None):
            if candidate.command_id == command_id:
                continue
            score = candidate_scores.get(candidate.command_id, 0)
            if record.family_key and candidate.family_key == record.family_key:
                score += 18
            shared_tags = len(set(record.tags).intersection(candidate.tags))
            if shared_tags:
                score += shared_tags * 6
            score += usage_map.get(candidate.command_id, 0)
            if score > 0:
                candidate_scores[candidate.command_id] = score
        ranked = sorted(candidate_scores.items(), key=lambda item: (-item[1], item[0]))
        return [command_id for command_id, _score in ranked[:limit]]

    def find_catalog_command_by_source_key(self, source_key: str) -> CommandRecord | None:
        cleaned_key = source_key.strip()
        if not cleaned_key:
            return None
        for record in self.list_commands(catalog_only=True, include_trashed=True):
            record_key = str(record.extra.get("source_key", "")).strip()
            if record_key and record_key == cleaned_key:
                return record
        return None
