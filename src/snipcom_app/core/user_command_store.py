from __future__ import annotations

import json
import uuid
from pathlib import Path

from .helpers import utc_now_iso


class UserCommandStore:
    VERSION = 1

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> dict:
        if not self._path.exists():
            return {"version": self.VERSION, "commands": []}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("commands"), list):
                return payload
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": self.VERSION, "commands": []}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_all(self) -> list[dict]:
        return list(self._load()["commands"])

    def create(self, title: str, body: str, description: str = "") -> dict:
        now = utc_now_iso()
        record: dict = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "body": body,
            "description": description.strip(),
            "folder_key": "",
            "created_at": now,
            "updated_at": now,
        }
        data = self._load()
        data["commands"].append(record)
        self._save(data)
        return record

    def get(self, uid: str) -> dict:
        for record in self._load()["commands"]:
            if record.get("id") == uid:
                return dict(record)
        raise KeyError(uid)

    def update(
        self,
        uid: str,
        *,
        title: str | None = None,
        body: str | None = None,
        description: str | None = None,
    ) -> dict:
        data = self._load()
        for record in data["commands"]:
            if record.get("id") == uid:
                if title is not None:
                    record["title"] = title.strip()
                if body is not None:
                    record["body"] = body
                if description is not None:
                    record["description"] = description.strip()
                record["updated_at"] = utc_now_iso()
                self._save(data)
                return dict(record)
        raise KeyError(uid)

    def set_folder(self, uid: str, folder_key: str) -> None:
        data = self._load()
        for record in data["commands"]:
            if record.get("id") == uid:
                record["folder_key"] = folder_key
                record["updated_at"] = utc_now_iso()
                self._save(data)
                return
        raise KeyError(uid)

    def set_tags(self, uid: str, tags: list[str]) -> None:
        data = self._load()
        for record in data["commands"]:
            if record.get("id") == uid:
                record["tags"] = tags
                record["updated_at"] = utc_now_iso()
                self._save(data)
                return
        raise KeyError(uid)

    def set_launch_options(self, uid: str, launch_options: dict) -> None:
        data = self._load()
        for record in data["commands"]:
            if record.get("id") == uid:
                record["launch_options"] = launch_options
                record["updated_at"] = utc_now_iso()
                self._save(data)
                return
        raise KeyError(uid)

    def delete(self, uid: str) -> None:
        data = self._load()
        data["commands"] = [r for r in data["commands"] if r.get("id") != uid]
        self._save(data)
