from __future__ import annotations

from dataclasses import dataclass


def normalize_command_snip_type(snip_type: str) -> str:
    return snip_type.strip()


@dataclass(frozen=True)
class CommandRecord:
    command_id: int
    slug: str
    title: str
    body: str
    snip_type: str
    family_key: str
    description: str
    source_kind: str
    source_ref: str
    source_license: str
    import_batch_id: int
    catalog_only: bool
    dangerous: bool
    launch_options: dict[str, object]
    trashed_at: str
    created_at: str
    updated_at: str
    extra: dict[str, object]
    tags: tuple[str, ...]

    @property
    def is_trashed(self) -> bool:
        return bool(self.trashed_at)


@dataclass(frozen=True)
class ImportSourceRecord:
    source_id: int
    name: str
    kind: str
    path_or_url: str
    is_git: bool
    local_checkout_path: str
    created_at: str
    updated_at: str
    last_sync_at: str
    last_status: str
    last_batch_id: int
