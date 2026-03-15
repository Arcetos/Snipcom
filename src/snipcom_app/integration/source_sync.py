from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..core.helpers import slugify_casefold, utc_now_iso
from .importers import (
    ImportBatchPayload,
    ImportedCommand,
    import_cheatsheets,
    import_internal_json_pack,
    import_navi_cheats,
    import_tldr_pages,
)
from ..core.repository import SnipcomRepository
def normalize_source_key(source_kind: str, source_ref: str, title: str) -> str:
    kind = source_kind.strip().casefold()
    source = " ".join(source_ref.strip().split()).casefold()
    normalized_title = " ".join(title.strip().split()).casefold()
    return f"{kind}|{source}|{normalized_title}"


def source_slug(text: str) -> str:
    return slugify_casefold(text) or "source"


def source_payload(source_kind: str, source_path: Path) -> ImportBatchPayload:
    cleaned_kind = source_kind.strip().casefold()
    if cleaned_kind == "navi-cheat":
        return import_navi_cheats(source_path)
    if cleaned_kind == "cheatsheet":
        return import_cheatsheets(source_path)
    if cleaned_kind == "tldr-pages":
        return import_tldr_pages(source_path)
    if cleaned_kind == "json-pack":
        return import_internal_json_pack(source_path)
    raise ValueError(f"Unsupported source kind: {source_kind}")


def upsert_import_payload(
    repository: SnipcomRepository,
    payload: ImportBatchPayload,
    *,
    source_ref_override: str | None = None,
    label_override: str | None = None,
    source_id: int = 0,
    source_name: str = "",
    purge_stale: bool = False,
) -> dict[str, int]:
    batch_id = repository.create_import_batch(
        label=label_override or payload.label,
        source_kind=payload.source_kind,
        source_ref=source_ref_override if source_ref_override is not None else payload.source_ref,
        source_license=payload.source_license,
        summary=payload.summary,
    )

    created = 0
    updated = 0
    skipped = 0
    seen_source_keys: set[str] = set()

    # Build a lookup dict once so we avoid an O(n²) scan for large payloads.
    existing_by_key: dict[str, object] = {
        str(rec.extra.get("source_key", "")).strip(): rec
        for rec in repository.command_store.list_commands(catalog_only=True, include_trashed=True)
        if str(rec.extra.get("source_key", "")).strip()
    }

    def effective_source_ref(command: ImportedCommand) -> str:
        if source_ref_override is not None:
            return source_ref_override
        if command.source_ref.strip():
            return command.source_ref.strip()
        return payload.source_ref

    for command in payload.commands:
        title = command.title.strip()
        body = command.body
        if not title or not body.strip():
            skipped += 1
            continue
        source_kind = (command.source_kind or payload.source_kind).strip() or payload.source_kind
        source_ref = effective_source_ref(command)
        source_key = normalize_source_key(source_kind, source_ref, title)
        seen_source_keys.add(source_key)

        extra = dict(command.extra)
        extra["source_key"] = source_key
        if source_id > 0:
            extra["source_id"] = source_id
        if source_name.strip():
            extra["source_name"] = source_name.strip()

        existing = existing_by_key.get(source_key)
        if existing is None:
            unique_title = repository.unique_command_title(title)
            repository.command_store.create_command(
                unique_title,
                body=body,
                snip_type=command.snip_type,
                family_key=command.family_key,
                description=command.description,
                source_kind=source_kind,
                source_ref=source_ref,
                source_license=command.source_license or payload.source_license,
                import_batch_id=batch_id,
                catalog_only=True,
                dangerous=False,
                tags=list(command.tags),
                extra=extra,
            )
            created += 1
            continue

        repository.command_store.update_command(
            existing.command_id,
            title=title,
            body=body,
            snip_type=command.snip_type,
            family_key=command.family_key,
            description=command.description,
            source_kind=source_kind,
            source_ref=source_ref,
            source_license=command.source_license or payload.source_license,
            import_batch_id=batch_id,
            catalog_only=True,
            dangerous=False,
            tags=list(command.tags),
            extra=extra,
        )
        updated += 1

    # Remove catalog commands from this source that no longer exist upstream.
    deleted = 0
    if purge_stale and source_id > 0 and seen_source_keys:
        for record in repository.command_store.list_commands(catalog_only=True, include_trashed=False):
            if int(record.extra.get("source_id", 0) or 0) != source_id:
                continue
            record_key = str(record.extra.get("source_key", "")).strip()
            if record_key and record_key not in seen_source_keys:
                repository.command_store.delete_command(record.command_id)
                deleted += 1

    return {"batch_id": batch_id, "created": created, "updated": updated, "skipped": skipped, "deleted": deleted}


def sync_import_source(
    repository: SnipcomRepository,
    *,
    source_id: int,
    app_support_dir: Path,
) -> dict[str, object]:
    source = repository.get_import_source(source_id)
    source_path = Path(source.path_or_url).expanduser()
    checkout_path = Path(source.local_checkout_path).expanduser() if source.local_checkout_path.strip() else None

    if source.is_git:
        git_checkout_root = app_support_dir / "import-sources" / "git"
        git_checkout_root.mkdir(parents=True, exist_ok=True)
        checkout_path = checkout_path or (git_checkout_root / source_slug(source.name))
        if not checkout_path.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", source.path_or_url, str(checkout_path)],
                check=True,
            )
        else:
            subprocess.run(["git", "-C", str(checkout_path), "pull", "--ff-only"], check=True)
        source_path = checkout_path

    payload = source_payload(source.kind, source_path)
    result = upsert_import_payload(
        repository,
        payload,
        source_ref_override=str(source_path),
        label_override=source.name,
        source_id=source.source_id,
        source_name=source.name,
        purge_stale=True,
    )
    repository.update_import_source(
        source.source_id,
        local_checkout_path=str(checkout_path) if checkout_path is not None else "",
        last_sync_at=utc_now_iso(),
        last_status="ok",
        last_batch_id=int(result["batch_id"]),
    )
    return {
        "source_id": source.source_id,
        "name": source.name,
        "batch_id": int(result["batch_id"]),
        "created": int(result["created"]),
        "updated": int(result["updated"]),
        "skipped": int(result["skipped"]),
        "deleted": int(result["deleted"]),
        "path": str(source_path),
    }
