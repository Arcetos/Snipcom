from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QColor

from ..core.helpers import FAVORITES_DEFAULT_COLOR, FAVORITES_TAG, has_tag, join_tags, normalize_launch_options, split_tags
from ..core.repository import SnipcomEntry
from ..core.snip_types import SNIP_TYPE_LABELS, SNIP_TYPE_ORDER

if TYPE_CHECKING:
    from .main_window import NoteCopyPaster


class MainWindowEntryMixin:
    def tag_color_overrides(self: "NoteCopyPaster") -> dict[str, str]:
        raw = self.settings.get("tag_colors", {})
        if not isinstance(raw, dict):
            return {}
        cleaned: dict[str, str] = {}
        for key, value in raw.items():
            tag = str(key).strip().casefold()
            if not tag:
                continue
            color = QColor(str(value).strip())
            if not color.isValid():
                continue
            cleaned[tag] = color.name(QColor.NameFormat.HexRgb)
        return cleaned

    def set_tag_color(self: "NoteCopyPaster", tag: str, color_value: str) -> None:
        key = tag.strip().casefold()
        if not key:
            return
        colors = self.tag_color_overrides()
        color = QColor(str(color_value).strip())
        if color.isValid():
            colors[key] = color.name(QColor.NameFormat.HexRgb)
        else:
            colors.pop(key, None)
        if colors:
            self.settings["tag_colors"] = colors
        else:
            self.settings.pop("tag_colors", None)
        self.save_settings()

    def clear_tag_color(self: "NoteCopyPaster", tag: str) -> None:
        key = tag.strip().casefold()
        if not key:
            return
        colors = self.tag_color_overrides()
        if key not in colors:
            return
        colors.pop(key, None)
        if colors:
            self.settings["tag_colors"] = colors
        else:
            self.settings.pop("tag_colors", None)
        self.save_settings()

    def tag_color_for_tag(self: "NoteCopyPaster", tag: str) -> str:
        key = tag.strip().casefold()
        if not key:
            return ""
        colors = self.tag_color_overrides()
        if key in colors:
            return colors[key]
        if key == FAVORITES_TAG:
            return FAVORITES_DEFAULT_COLOR
        return ""

    def entry_tag_color(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        colors = self.tag_color_overrides()
        for tag in self.tags_for(target):
            key = tag.strip().casefold()
            if not key:
                continue
            if key in colors:
                return colors[key]
            if key == FAVORITES_TAG:
                return FAVORITES_DEFAULT_COLOR
        return ""

    def entry_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str | None) -> SnipcomEntry | None:
        if target is None:
            return None
        if isinstance(target, SnipcomEntry):
            return self.repository.entry_from_id(target.entry_id, self.tags, self.snip_types) or target
        if isinstance(target, Path):
            entry_id = self.repository.folder_entry_id(target) if target.is_dir() else self.repository.file_entry_id(target)
            return self.repository.entry_from_id(entry_id, self.tags, self.snip_types)
        if isinstance(target, str):
            return self.repository.entry_from_id(target, self.tags, self.snip_types)
        return None

    def tag_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None:
            return ""
        if entry.is_command:
            return entry.tag_text
        assert entry.path is not None
        return self.tags.get(self.repository.storage_key(entry.path), "")

    def snip_type_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None:
            return "text_file"
        if entry.is_command:
            return entry.snip_type
        assert entry.path is not None
        return self.snip_types.get(self.repository.storage_key(entry.path), "text_file")

    def snip_type_label_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        return SNIP_TYPE_LABELS.get(self.snip_type_for(target), SNIP_TYPE_LABELS["text_file"])

    def tags_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> list[str]:
        return split_tags(self.tag_for(target))

    def is_favorite(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> bool:
        return has_tag(self.tags_for(target), FAVORITES_TAG)

    def description_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None or not entry.is_command or entry.command_id is None:
            return ""
        try:
            return self.repository.command_store.get_command(entry.command_id).description.strip()
        except KeyError:
            return ""

    def family_badge_text_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None or not entry.is_command:
            return ""
        if entry.snip_type == "family_command" and entry.family_key:
            return entry.family_key
        return "General"

    def family_label_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None:
            return ""
        if entry.is_folder:
            return "folder"
        if entry.is_file:
            return "txt"
        if entry.snip_type == "family_command" and entry.family_key:
            return entry.family_key
        return "general"

    def primary_text_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        return self.display_name(target)

    def secondary_text_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is None:
            return ""
        if entry.is_folder:
            item_label = "item" if entry.size_bytes == 1 else "items"
            return f"Popup folder . {entry.size_bytes} {item_label}"
        description = self.description_for(entry)
        if description:
            return description
        if entry.is_command and entry.family_key:
            return entry.family_key
        return ""

    def set_tag(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, tag: str) -> None:
        entry = self.entry_for(target)
        if entry is None:
            return
        if entry.is_folder:
            return
        current_tags = self.tags_for(entry)
        cleaned_tags = split_tags(tag)
        cleaned_tags = [FAVORITES_TAG if existing.casefold() == FAVORITES_TAG else existing for existing in cleaned_tags]
        if has_tag(current_tags, FAVORITES_TAG) and not has_tag(cleaned_tags, FAVORITES_TAG):
            cleaned_tags.append(FAVORITES_TAG)
        cleaned_tag = join_tags(cleaned_tags)
        if entry.is_command:
            assert entry.command_id is not None
            self.repository.command_store.update_command(entry.command_id, tags=split_tags(cleaned_tag))
            return
        assert entry.path is not None
        key = self.repository.storage_key(entry.path)
        if cleaned_tag:
            self.tags[key] = cleaned_tag
        else:
            self.tags.pop(key, None)
        self.save_tags()

    def set_snip_type(self: "NoteCopyPaster", target: SnipcomEntry | Path | str, snip_type: str) -> None:
        entry = self.entry_for(target)
        if entry is None:
            return
        if entry.is_folder:
            return
        if snip_type not in SNIP_TYPE_ORDER:
            snip_type = "text_file"
        if entry.is_command:
            if snip_type != "text_file":
                assert entry.command_id is not None
                self.repository.command_store.update_command(entry.command_id, snip_type=snip_type)
            return
        assert entry.path is not None
        key = self.repository.storage_key(entry.path)
        self.snip_types[key] = snip_type
        self.save_snip_types()

    def move_tag(self: "NoteCopyPaster", old_path: Path, new_path: Path) -> None:
        self.repository.move_metadata(self.tags, self.snip_types, self.launch_options, old_path, new_path)
        self.save_tags()
        self.save_snip_types()
        self.save_launch_options()

    def remove_tag(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> None:
        entry = self.entry_for(target)
        if entry is None:
            return
        if entry.is_folder:
            return
        if self.is_favorite(entry):
            return
        if entry.is_command:
            assert entry.command_id is not None
            self.repository.command_store.update_command(entry.command_id, tags=[])
            return
        assert entry.path is not None
        self.repository.remove_metadata(self.tags, self.snip_types, self.launch_options, entry.path)
        self.save_tags()
        self.save_snip_types()
        self.save_launch_options()

    def add_to_favorites(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> bool:
        entry = self.entry_for(target)
        if entry is None or entry.is_folder:
            return False
        existing_tags = self.tags_for(entry)
        if has_tag(existing_tags, FAVORITES_TAG):
            return False
        updated_tags = [FAVORITES_TAG if tag.casefold() == FAVORITES_TAG else tag for tag in existing_tags]
        updated_tags.append(FAVORITES_TAG)
        self.set_tag(entry, join_tags(updated_tags))
        return True

    def remove_from_favorites(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> bool:
        entry = self.entry_for(target)
        if entry is None or entry.is_folder:
            return False
        existing_tags = self.tags_for(entry)
        if not has_tag(existing_tags, FAVORITES_TAG):
            return False
        updated_tags = [tag for tag in existing_tags if tag.strip().casefold() != FAVORITES_TAG]
        if entry.is_command:
            assert entry.command_id is not None
            self.repository.command_store.update_command(entry.command_id, tags=updated_tags)
            return True
        assert entry.path is not None
        key = self.repository.storage_key(entry.path)
        cleaned_tag = join_tags(updated_tags)
        if cleaned_tag:
            self.tags[key] = cleaned_tag
        else:
            self.tags.pop(key, None)
        self.save_tags()
        return True

    def launch_options_for(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> dict[str, object]:
        entry = self.entry_for(target)
        if entry is None:
            return normalize_launch_options(None)
        if entry.is_folder:
            return normalize_launch_options(None)
        if entry.entry_id.startswith("json_command:"):
            uid = entry.entry_id[len("json_command:"):]
            try:
                d = self.repository.user_command_store.get(uid)
                return normalize_launch_options(d.get("launch_options") or {})
            except KeyError:
                return normalize_launch_options(None)
        if entry.is_command:
            assert entry.command_id is not None
            return self.repository.command_store.get_command(entry.command_id).launch_options
        assert entry.path is not None
        options = self.launch_options.get(self.repository.storage_key(entry.path), {})
        return normalize_launch_options(options)

    def set_launch_options(
        self: "NoteCopyPaster",
        target: SnipcomEntry | Path | str,
        *,
        keep_open: bool,
        ask_extra_arguments: bool,
        copy_output_and_close: bool,
        use_linked_terminal: bool = True,
    ) -> None:
        entry = self.entry_for(target)
        if entry is None:
            return
        if entry.is_folder:
            return
        normalized = normalize_launch_options(
            {
                "keep_open": keep_open,
                "ask_extra_arguments": ask_extra_arguments,
                "copy_output_and_close": copy_output_and_close,
                "use_linked_terminal": use_linked_terminal,
            }
        )
        if entry.entry_id.startswith("json_command:"):
            uid = entry.entry_id[len("json_command:"):]
            try:
                self.repository.user_command_store.set_launch_options(uid, normalized)
            except KeyError:
                pass
            return
        if entry.is_command:
            assert entry.command_id is not None
            self.repository.command_store.update_command(entry.command_id, launch_options=normalized)
            return
        assert entry.path is not None
        self.launch_options[self.repository.storage_key(entry.path)] = normalized
        self.save_launch_options()

    def display_name(self: "NoteCopyPaster", target: SnipcomEntry | Path | str) -> str:
        entry = self.entry_for(target)
        if entry is not None:
            return entry.display_name
        if isinstance(target, Path):
            if target.suffix.casefold() == ".txt":
                return target.stem
            return target.name
        return str(target)
