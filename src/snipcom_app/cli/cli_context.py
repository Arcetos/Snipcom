from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.profiles import ProfileManager
from ..core.repository import SnipcomRepository


APP_SUPPORT_DIR = Path.home() / ".local" / "share" / "snipcom"
APP_CONFIG_DIR = Path.home() / ".config" / "snipcom"
DEFAULT_TEXTS_DIR = APP_SUPPORT_DIR / "texts"
DEFAULT_SETTINGS_FILE = APP_CONFIG_DIR / "settings.json"
CLI_STATE_DIR = APP_SUPPORT_DIR / "cli-state"
DEFAULT_PREVIEW_LINES = 30


@dataclass
class CliContext:
    profile_slug: str
    repository: SnipcomRepository
    settings: dict[str, object]
    tags: dict[str, str]
    snip_types: dict[str, str]
    launch_options: dict[str, dict[str, object]]
    _catalog_cache: list | None = field(default=None, repr=False)
    _usage_cache: dict | None = field(default=None, repr=False)

    def cached_catalog_entries(self) -> list:
        if self._catalog_cache is None:
            self._catalog_cache = self.repository.catalog_entries(include_active_commands=True)
        return self._catalog_cache

    def cached_usage_counts(self) -> dict:
        if self._usage_cache is None:
            self._usage_cache = self.repository.command_store.usage_counts()
        return self._usage_cache


def _load_json_dict(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items()}


def _save_json_dict(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _profile_manager() -> ProfileManager:
    return ProfileManager(
        app_support_dir=APP_SUPPORT_DIR,
        app_config_dir=APP_CONFIG_DIR,
        default_settings_path=DEFAULT_SETTINGS_FILE,
        default_texts_dir=DEFAULT_TEXTS_DIR,
    )


def _settings_for_profile(profile_manager: ProfileManager, profile_slug: str) -> dict[str, object]:
    settings_path = profile_manager.settings_path(profile_slug)
    return _load_json_dict(settings_path)


def _texts_dir_for_profile(profile_manager: ProfileManager, profile_slug: str, settings: dict[str, object]) -> Path:
    configured = str(settings.get("texts_dir", "")).strip()
    if configured:
        return Path(configured).expanduser()
    return profile_manager.default_texts_dir(profile_slug)


def _context(profile_slug: str) -> CliContext:
    profile_manager = _profile_manager()
    slug = profile_slug.strip() or profile_manager.current_profile_slug
    if slug not in {profile.slug for profile in profile_manager.list_profiles()}:
        raise ValueError(f"Unknown profile: {slug}")
    settings = _settings_for_profile(profile_manager, slug)
    texts_dir = _texts_dir_for_profile(profile_manager, slug, settings)
    repository = SnipcomRepository(texts_dir)
    repository.ensure_storage()
    return CliContext(
        profile_slug=slug,
        repository=repository,
        settings=settings,
        tags=repository.load_tags(),
        snip_types=repository.load_snip_types(),
        launch_options=repository.load_launch_options(),
    )


def _state_path(profile_slug: str) -> Path:
    slug = profile_slug.strip() or "default"
    return CLI_STATE_DIR / f"{slug}.json"


def _state_payload(profile_slug: str) -> dict[str, object]:
    return _load_json_dict(_state_path(profile_slug))


def _set_last_selection(profile_slug: str, entry_id: str, display_name: str) -> None:
    payload = _state_payload(profile_slug)
    payload["last_selection"] = {
        "entry_id": entry_id,
        "name": display_name,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    _save_json_dict(_state_path(profile_slug), payload)


def _last_selection_entry_id(profile_slug: str) -> str:
    payload = _state_payload(profile_slug)
    selection = payload.get("last_selection")
    if not isinstance(selection, dict):
        return ""
    return str(selection.get("entry_id", "")).strip()
