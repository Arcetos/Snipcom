from __future__ import annotations

import json
from pathlib import Path

from .command_store_models import normalize_command_snip_type
from .helpers import join_tags, normalize_launch_options, read_json_file, split_tags


class RepositoryMetadataMixin:
    # These attributes are set by SnipcomRepository.set_texts_dir():
    tags_file: Path
    descriptions_file: Path
    snip_types_file: Path
    launch_options_file: Path

    # VALID_SNIP_TYPES is defined on SnipcomRepository
    VALID_SNIP_TYPES: set[str]

    def load_tags(self) -> dict[str, str]:
        data = read_json_file(self.tags_file)
        normalized_tags: dict[str, str] = {}
        for key, value in data.items():
            normalized_value = join_tags(split_tags(str(value)))
            if normalized_value:
                normalized_tags[str(key)] = normalized_value
        return normalized_tags

    def save_tags(self, tags: dict[str, str]) -> None:
        if not tags:
            try:
                self.tags_file.unlink()
            except FileNotFoundError:
                pass
            return
        self.tags_file.write_text(json.dumps(tags, indent=2, sort_keys=True), encoding="utf-8")

    def load_descriptions(self) -> dict[str, str]:
        data = read_json_file(self.descriptions_file)
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}

    def save_descriptions(self, descriptions: dict[str, str]) -> None:
        if not descriptions:
            try:
                self.descriptions_file.unlink()
            except FileNotFoundError:
                pass
            return
        self.descriptions_file.write_text(json.dumps(descriptions, indent=2, sort_keys=True), encoding="utf-8")

    def load_snip_types(self) -> dict[str, str]:
        data = read_json_file(self.snip_types_file)
        snip_types: dict[str, str] = {}
        for key, value in data.items():
            raw_value = str(value).strip()
            value_text = normalize_command_snip_type(raw_value)
            if value_text in self.VALID_SNIP_TYPES:
                snip_types[str(key)] = value_text
        return snip_types

    def save_snip_types(self, snip_types: dict[str, str]) -> None:
        if not snip_types:
            try:
                self.snip_types_file.unlink()
            except FileNotFoundError:
                pass
            return
        cleaned = {key: value for key, value in snip_types.items() if value in self.VALID_SNIP_TYPES}
        self.snip_types_file.write_text(json.dumps(cleaned, indent=2, sort_keys=True), encoding="utf-8")

    def load_launch_options(self) -> dict[str, dict[str, object]]:
        data = read_json_file(self.launch_options_file)
        launch_options: dict[str, dict[str, object]] = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            launch_options[str(key)] = normalize_launch_options(value)
        return launch_options

    def save_launch_options(self, launch_options: dict[str, dict[str, object]]) -> None:
        if not launch_options:
            try:
                self.launch_options_file.unlink()
            except FileNotFoundError:
                pass
            return
        self.launch_options_file.write_text(json.dumps(launch_options, indent=2, sort_keys=True), encoding="utf-8")

    def move_metadata(
        self,
        tags: dict[str, str],
        snip_types: dict[str, str],
        launch_options: dict[str, dict[str, object]],
        old_path: Path,
        new_path: Path,
    ) -> None:
        old_key = self.storage_key(old_path)  # type: ignore[attr-defined]
        new_key = self.storage_key(new_path)  # type: ignore[attr-defined]
        self._move_metadata_map(tags, old_key, new_key)
        self._move_metadata_map(snip_types, old_key, new_key)
        self._move_metadata_map(launch_options, old_key, new_key)

    def remove_metadata(
        self,
        tags: dict[str, str],
        snip_types: dict[str, str],
        launch_options: dict[str, dict[str, object]],
        path: Path,
    ) -> None:
        key = self.storage_key(path)  # type: ignore[attr-defined]
        self._remove_metadata_map(tags, key)
        self._remove_metadata_map(snip_types, key)
        self._remove_metadata_map(launch_options, key)

    def _move_metadata_map(self, mapping: dict, old_key: str, new_key: str) -> None:
        old_prefix = f"{old_key}/"
        updates = []
        removals = []
        for key, value in mapping.items():
            if key == old_key:
                updates.append((new_key, value))
                removals.append(key)
            elif key.startswith(old_prefix):
                updates.append((f"{new_key}/{key[len(old_prefix):]}", value))
                removals.append(key)
        for key in removals:
            mapping.pop(key, None)
        for key, value in updates:
            mapping[key] = value

    def _remove_metadata_map(self, mapping: dict, key: str) -> None:
        prefix = f"{key}/"
        removals = [item_key for item_key in mapping if item_key == key or item_key.startswith(prefix)]
        for item_key in removals:
            mapping.pop(item_key, None)
