from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .helpers import slugify_casefold


DEFAULT_PROFILE_SLUG = "default"


@dataclass(frozen=True)
class SnipcomProfile:
    slug: str
    display_name: str

    @property
    def is_default(self) -> bool:
        return self.slug == DEFAULT_PROFILE_SLUG


class ProfileManager:
    def __init__(
        self,
        *,
        app_support_dir: Path,
        app_config_dir: Path,
        default_settings_path: Path,
        default_texts_dir: Path,
    ) -> None:
        self.app_support_dir = app_support_dir
        self.app_config_dir = app_config_dir
        self.default_settings_path = default_settings_path
        self.default_texts_dir_path = default_texts_dir
        self.registry_path = self.app_config_dir / "profiles.json"
        self.profile_config_root = self.app_config_dir / "profiles"
        self.profile_support_root = self.app_support_dir / "profiles"
        self.current_profile_slug = DEFAULT_PROFILE_SLUG
        self._profiles: dict[str, SnipcomProfile] = {}
        self.load_registry()

    def load_registry(self) -> None:
        if not self.registry_path.exists():
            self._profiles = {
                DEFAULT_PROFILE_SLUG: SnipcomProfile(DEFAULT_PROFILE_SLUG, "Default"),
            }
            self.current_profile_slug = DEFAULT_PROFILE_SLUG
            self.save_registry()
            return

        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}

        raw_profiles = payload.get("profiles", {}) if isinstance(payload, dict) else {}
        profiles: dict[str, SnipcomProfile] = {}
        if isinstance(raw_profiles, dict):
            for slug, value in raw_profiles.items():
                slug_text = str(slug).strip()
                if not slug_text:
                    continue
                display_name = str(value.get("display_name", slug_text)).strip() if isinstance(value, dict) else slug_text
                profiles[slug_text] = SnipcomProfile(slug_text, display_name or slug_text)

        if DEFAULT_PROFILE_SLUG not in profiles:
            profiles[DEFAULT_PROFILE_SLUG] = SnipcomProfile(DEFAULT_PROFILE_SLUG, "Default")

        self._profiles = profiles
        current_profile = str(payload.get("current_profile", DEFAULT_PROFILE_SLUG)).strip() if isinstance(payload, dict) else DEFAULT_PROFILE_SLUG
        self.current_profile_slug = current_profile if current_profile in self._profiles else DEFAULT_PROFILE_SLUG
        self.save_registry()

    def save_registry(self) -> None:
        self.app_config_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "current_profile": self.current_profile_slug,
            "profiles": {
                slug: {"display_name": profile.display_name}
                for slug, profile in sorted(self._profiles.items(), key=lambda item: (item[0] != DEFAULT_PROFILE_SLUG, item[1].display_name.casefold()))
            },
        }
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list_profiles(self) -> list[SnipcomProfile]:
        profiles = list(self._profiles.values())
        profiles.sort(key=lambda profile: (profile.slug != DEFAULT_PROFILE_SLUG, profile.display_name.casefold(), profile.slug))
        return profiles

    def current_profile(self) -> SnipcomProfile:
        return self._profiles[self.current_profile_slug]

    def settings_path(self, slug: str | None = None) -> Path:
        slug = slug or self.current_profile_slug
        if slug == DEFAULT_PROFILE_SLUG:
            return self.default_settings_path
        return self.profile_config_root / slug / "settings.json"

    def profile_root_dir(self, slug: str | None = None) -> Path:
        slug = slug or self.current_profile_slug
        if slug == DEFAULT_PROFILE_SLUG:
            return self.app_support_dir
        return self.profile_support_root / slug

    def default_texts_dir(self, slug: str | None = None) -> Path:
        slug = slug or self.current_profile_slug
        if slug == DEFAULT_PROFILE_SLUG:
            return self.default_texts_dir_path
        return self.profile_root_dir(slug) / "texts"

    def switch_profile(self, slug: str) -> SnipcomProfile:
        if slug not in self._profiles:
            raise KeyError(slug)
        self.current_profile_slug = slug
        self.save_registry()
        return self._profiles[slug]

    def create_profile(self, display_name: str) -> SnipcomProfile:
        cleaned_name = display_name.strip()
        if not cleaned_name:
            raise ValueError("Profile name cannot be empty.")

        slug = self._unique_slug(cleaned_name)
        profile = SnipcomProfile(slug, cleaned_name)
        self._profiles[slug] = profile
        self.profile_config_root.mkdir(parents=True, exist_ok=True)
        self.profile_support_root.mkdir(parents=True, exist_ok=True)
        self.default_texts_dir(slug).mkdir(parents=True, exist_ok=True)
        self.save_registry()
        return profile

    def delete_profile(self, slug: str) -> None:
        if slug == DEFAULT_PROFILE_SLUG:
            raise ValueError("Default profile cannot be deleted.")
        if slug not in self._profiles:
            raise KeyError(slug)
        settings_path = self.settings_path(slug)
        if settings_path.exists():
            shutil.rmtree(settings_path.parent, ignore_errors=True)
        profile_root = self.profile_root_dir(slug)
        if profile_root.exists():
            shutil.rmtree(profile_root, ignore_errors=True)
        self._profiles.pop(slug, None)
        if self.current_profile_slug == slug:
            self.current_profile_slug = DEFAULT_PROFILE_SLUG
        self.save_registry()

    def reset_profile(self, slug: str) -> None:
        texts_dir = self.default_texts_dir(slug)
        if texts_dir.exists():
            shutil.rmtree(texts_dir, ignore_errors=True)
        texts_dir.mkdir(parents=True, exist_ok=True)

        settings_path = self.settings_path(slug)
        if settings_path.exists():
            try:
                settings_path.unlink()
            except IsADirectoryError:
                shutil.rmtree(settings_path.parent, ignore_errors=True)
        if slug != DEFAULT_PROFILE_SLUG:
            profile_root = self.profile_root_dir(slug)
            profile_root.mkdir(parents=True, exist_ok=True)

    def _unique_slug(self, display_name: str) -> str:
        base = self._slugify(display_name) or "profile"
        slug = base
        suffix = 2
        while slug in self._profiles:
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    def _slugify(self, text: str) -> str:
        return slugify_casefold(text)
