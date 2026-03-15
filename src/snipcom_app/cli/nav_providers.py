from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..ai.ai_shared import (
    ai_anchor_terms,
    ai_enabled,
    ai_endpoint,
    ai_model,
    ai_provider,
    ai_timeout_seconds,
    primary_tool_for_ai,
)
from ..core.helpers import FAVORITES_TAG, has_tag, natural_request_text, split_tags
from ..core.repository import SnipcomEntry
from .cli_context import CliContext, _last_selection_entry_id
from .cli_entries import _entry_text, _query_matches_entry, _search_score, _workflow_entries


# ---------------------------------------------------------------------------
# Color pair constants (referenced by nav_tui.py for curses color initialization)
# ---------------------------------------------------------------------------

NAV_PAIR_DEFAULT = 1
NAV_PAIR_INPUT = 2
NAV_PAIR_HEADER = 3
NAV_PAIR_WORKFLOW = 4
NAV_PAIR_HEURISTIC = 5
NAV_PAIR_AI = 6
NAV_PAIR_STATUS = 7
NAV_PAIR_GHOST = 8


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class NavigatorCandidate:
    entry: SnipcomEntry
    source_label: str
    source_rank: int
    score: int
    reason: str
    body: str


@dataclass(frozen=True)
class NavigatorSection:
    title: str
    source_label: str
    candidates: list[NavigatorCandidate]
    empty_message: str = "[no results]"


@dataclass(frozen=True)
class NavigatorOutcome:
    action: str
    candidate: NavigatorCandidate | None
    command_text: str


@dataclass
class NavigatorAIState:
    request_text: str = ""
    busy: bool = False
    error_message: str = ""
    candidates: list[NavigatorCandidate] = field(default_factory=list)
    generation_id: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _synthetic_entry(
    display_name: str,
    *,
    entry_id: str,
    snip_type: str = "family_command",
    family_key: str = "",
    source_kind: str = "",
) -> SnipcomEntry:
    return SnipcomEntry(
        entry_id=entry_id,
        backend="synthetic",
        name=display_name,
        display_name=display_name,
        snip_type=snip_type,
        tag_text="",
        size_bytes=len(display_name.encode("utf-8")),
        modified_timestamp=0.0,
        dangerous=False,
        family_key=family_key,
        source_kind=source_kind,
    )


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def _natural_request_text(text: str) -> str:
    return natural_request_text(text)


def _effective_nav_query(query: str) -> str:
    return _natural_request_text(query) or query.strip()


# ---------------------------------------------------------------------------
# AI settings wrappers
# ---------------------------------------------------------------------------

def _ai_enabled(ctx: CliContext) -> bool:
    return ai_enabled(ctx.settings)


def _ai_provider(ctx: CliContext) -> str:
    return ai_provider(ctx.settings)


def _ai_endpoint(ctx: CliContext) -> str:
    return ai_endpoint(ctx.settings)


def _ai_model(ctx: CliContext) -> str:
    return ai_model(ctx.settings)


def _ai_timeout_seconds(ctx: CliContext) -> int:
    return ai_timeout_seconds(ctx.settings)


def _ai_anchor_terms(*values: str) -> list[str]:
    return ai_anchor_terms(*values)


def _primary_tool_for_ai(ctx: CliContext, last_terminal_input: str, user_request: str) -> str:
    return primary_tool_for_ai(
        ctx.repository.catalog_entries(include_active_commands=True),
        last_terminal_input,
        user_request,
    )


# ---------------------------------------------------------------------------
# AI context helpers
# ---------------------------------------------------------------------------

def _read_directory_files(cwd: str) -> tuple[str, ...]:
    if not cwd:
        return ()
    try:
        p = Path(cwd)
        if not p.is_dir():
            return ()
        names: list[str] = []
        for child in p.iterdir():
            name = child.name
            if name.startswith("."):
                continue
            names.append(name + "/" if child.is_dir() else name)
        return tuple(sorted(names)[:50])
    except OSError:
        return ()


def _collect_related_commands_for_ai(
    ctx: CliContext,
    last_terminal_input: str,
    user_request: str,
    primary_tool: str,
) -> list[str]:
    related: list[str] = []
    candidate_ids: list[int] = []
    last_entry_id = _last_selection_entry_id(ctx.profile_slug)
    last_entry = ctx.repository.entry_from_id(last_entry_id, ctx.tags, ctx.snip_types, include_trashed=False) if last_entry_id else None
    if last_entry is not None and last_entry.command_id is not None:
        candidate_ids.extend(ctx.repository.command_store.related_command_ids(last_entry.command_id, limit=6))
    query_terms: list[str] = []
    if last_terminal_input.strip():
        query_terms.append(last_terminal_input.strip())
    if user_request.strip():
        query_terms.append(user_request.strip())
    seen_ids: set[int] = set(candidate_ids)
    token_terms = _ai_anchor_terms(*query_terms[:3])
    for query in query_terms[:3]:
        lowered_query = query.casefold()
        for entry in ctx.repository.catalog_entries(include_active_commands=True):
            if not entry.is_command or entry.command_id is None or entry.command_id in seen_ids:
                continue
            entry_name = entry.display_name.casefold()
            entry_family = entry.family_key.casefold()
            entry_tags = entry.tag_text.casefold()
            if primary_tool and primary_tool not in entry_name and primary_tool not in entry_family and primary_tool not in entry_tags:
                continue
            if (
                lowered_query in entry_name
                or lowered_query in entry_family
                or any(token in entry_name or token in entry_family or token in entry_tags for token in token_terms)
            ):
                candidate_ids.append(entry.command_id)
                seen_ids.add(entry.command_id)
            if len(candidate_ids) >= 10:
                break
        if len(candidate_ids) >= 10:
            break
    for command_id in candidate_ids[:8]:
        entry = ctx.repository.entry_from_id(
            ctx.repository.command_entry_id(command_id),
            ctx.tags,
            ctx.snip_types,
        )
        if entry is not None:
            body = _entry_text(ctx, entry).strip()
            if body:
                related.append(body)
    return related


def _build_cli_ai_context(ctx: CliContext, user_request: str):  # -> AISuggestionContext
    from ..ai.ai import AISuggestionContext
    current_directory = os.getcwd()
    directory_files = _read_directory_files(current_directory)
    last_entry_id = _last_selection_entry_id(ctx.profile_slug)
    last_entry = ctx.repository.entry_from_id(last_entry_id, ctx.tags, ctx.snip_types, include_trashed=False) if last_entry_id else None
    last_terminal_input = _entry_text(ctx, last_entry).strip() if last_entry is not None else ""
    primary_tool = _primary_tool_for_ai(ctx, last_terminal_input, user_request)
    related_commands = tuple(
        _collect_related_commands_for_ai(ctx, last_terminal_input, user_request, primary_tool)
    )
    return AISuggestionContext(
        user_request=user_request.strip(),
        last_terminal_input=last_terminal_input,
        last_terminal_output="",
        primary_tool=primary_tool,
        recent_searches=(),
        related_commands=related_commands,
        current_directory=current_directory,
        directory_files=directory_files,
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _nav_recency_bonus(entry: SnipcomEntry) -> int:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).timestamp()
    age_hours = max(0.0, (now - float(entry.modified_timestamp or 0.0)) / 3600.0)
    if age_hours <= 24:
        return 18
    if age_hours <= 24 * 3:
        return 10
    if age_hours <= 24 * 7:
        return 5
    return 0


def _nav_match_score(query: str, entry: SnipcomEntry, body: str, usage_count: int) -> int:
    base = _search_score(query, entry, body, usage_count)
    if not query.strip():
        base += _nav_recency_bonus(entry)
        if has_tag(split_tags(entry.tag_text), FAVORITES_TAG):
            base += 10
    return base


# ---------------------------------------------------------------------------
# CWD helper
# ---------------------------------------------------------------------------

def _cwd_tokens() -> list[str]:
    tokens: list[str] = []
    for part in os.getcwd().split(os.sep)[-3:]:
        cleaned = part.strip().casefold()
        if cleaned and cleaned not in {"/", ".", ".."}:
            tokens.append(cleaned)
    return tokens


# ---------------------------------------------------------------------------
# Candidate text helpers
# ---------------------------------------------------------------------------

def _candidate_command_text(candidate: NavigatorCandidate) -> str:
    body = " ".join(candidate.body.splitlines()).strip()
    return body or candidate.entry.display_name


def _candidate_return_text(candidate: NavigatorCandidate) -> str:
    body = candidate.body.strip()
    return body or candidate.entry.display_name


def _candidate_description_text(candidate: NavigatorCandidate, descriptions: dict[str, str]) -> str:
    entry = candidate.entry
    if entry.is_command:
        desc = entry.description.strip()
    else:
        # descriptions.json is keyed by storage_key (e.g. "cla.txt"), not entry_id ("file:cla.txt")
        storage_key = entry.entry_id.partition(":")[2]
        desc = descriptions.get(storage_key, "").strip()
    if desc:
        return desc
    if entry.tag_text.strip():
        return entry.tag_text.strip()
    return entry.snip_type.replace("_", " ")


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def _workflow_provider(ctx: CliContext, query: str, *, limit: int) -> list[NavigatorCandidate]:
    usage_counts = ctx.cached_usage_counts()
    query_text = query.strip()
    candidates: list[NavigatorCandidate] = []
    for entry in _workflow_entries(ctx):
        body = _entry_text(ctx, entry)
        if query_text and not _query_matches_entry(ctx, entry, query_text):
            continue
        reason_parts: list[str] = []
        if has_tag(split_tags(entry.tag_text), FAVORITES_TAG):
            reason_parts.append("favorite")
        if entry.is_command and usage_counts.get(entry.command_id or -1, 0) >= 3:
            reason_parts.append("used often")
        candidates.append(
            NavigatorCandidate(
                entry=entry,
                source_label="workflow",
                source_rank=0,
                score=40 + _nav_match_score(query, entry, body, usage_counts.get(entry.command_id or -1, 0)),
                reason=", ".join(reason_parts[:2]),
                body=body,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.entry.display_name.casefold(), item.entry.entry_id))
    return candidates[: max(1, limit)]


def _context_provider(ctx: CliContext, query: str, *, limit: int) -> list[NavigatorCandidate]:
    usage_counts = ctx.cached_usage_counts()
    query_text = query.strip()
    cwd_tokens = _cwd_tokens()
    last_entry_id = _last_selection_entry_id(ctx.profile_slug)
    related_ids: set[int] = set()
    if last_entry_id.startswith("command:"):
        related_ids = set(ctx.repository.command_store.related_command_ids(int(last_entry_id.partition(":")[2]), limit=10))

    candidates: list[NavigatorCandidate] = []
    for entry in _workflow_entries(ctx):
        body = _entry_text(ctx, entry)
        if query_text and not _query_matches_entry(ctx, entry, query_text):
            continue
        score = 0
        reasons: list[str] = []
        if entry.command_id is not None and entry.command_id in related_ids:
            score += 42
            reasons.append("related to last selection")
        joined_fields = " ".join(
            (
                entry.display_name.casefold(),
                entry.tag_text.casefold(),
                entry.family_key.casefold(),
                body.casefold(),
            )
        )
        matched_cwd = next((token for token in cwd_tokens if token and token in joined_fields), "")
        if matched_cwd:
            score += 26
            reasons.append(f"matches cwd: {matched_cwd}")
        usage_count = usage_counts.get(entry.command_id or -1, 0)
        if not query_text and usage_count >= 2:
            score += min(usage_count, 8) * 4
            reasons.append("frequently used")
        if not query_text and has_tag(split_tags(entry.tag_text), FAVORITES_TAG):
            score += 12
            reasons.append("favorite")
        if score <= 0:
            continue
        candidates.append(
            NavigatorCandidate(
                entry=entry,
                source_label="context",
                source_rank=1,
                score=score + _nav_match_score(query, entry, body, usage_count),
                reason=", ".join(reasons[:2]),
                body=body,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.entry.display_name.casefold(), item.entry.entry_id))
    return candidates[: max(1, limit)]


def _database_provider(ctx: CliContext, query: str, *, limit: int) -> list[NavigatorCandidate]:
    query_text = query.strip()
    if not query_text:
        return []
    usage_counts = ctx.cached_usage_counts()
    # Use FTS5 for fast full-text search; fall back to cached linear scan if FTS returns nothing
    fts_records = ctx.repository.command_store.search_commands_fts(query_text, limit=limit * 4)
    if fts_records:
        repo = ctx.repository
        candidates: list[NavigatorCandidate] = []
        for record in fts_records:
            entry = repo.command_entry_from_record(record)
            body = entry.body
            candidates.append(
                NavigatorCandidate(
                    entry=entry,
                    source_label="database",
                    source_rank=2,
                    score=10 + _nav_match_score(query, entry, body, usage_counts.get(entry.command_id or -1, 0)),
                    reason="catalog suggestion",
                    body=body,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.entry.display_name.casefold(), item.entry.entry_id))
        return candidates[: max(1, limit)]
    # Fallback: cached linear scan (covers entries not yet indexed by FTS)
    candidates = []
    for entry in ctx.cached_catalog_entries():
        if entry.is_folder or not _query_matches_entry(ctx, entry, query_text):
            continue
        body = _entry_text(ctx, entry)
        candidates.append(
            NavigatorCandidate(
                entry=entry,
                source_label="database",
                source_rank=2,
                score=10 + _nav_match_score(query, entry, body, usage_counts.get(entry.command_id or -1, 0)),
                reason="catalog suggestion",
                body=body,
            )
        )
    candidates.sort(key=lambda item: (-item.score, item.entry.display_name.casefold(), item.entry.entry_id))
    return candidates[: max(1, limit)]


# ---------------------------------------------------------------------------
# Merge and section builders
# ---------------------------------------------------------------------------

def _merge_nav_candidates(
    workflow_candidates: list[NavigatorCandidate],
    context_candidates: list[NavigatorCandidate],
    database_candidates: list[NavigatorCandidate],
    *,
    limit: int,
) -> list[NavigatorCandidate]:
    merged: dict[str, NavigatorCandidate] = {candidate.entry.entry_id: candidate for candidate in workflow_candidates}
    for candidate in context_candidates:
        existing = merged.get(candidate.entry.entry_id)
        if existing is None:
            merged[candidate.entry.entry_id] = candidate
            continue
        existing.score += max(1, candidate.score // 3)
        if candidate.reason:
            reasons = [part.strip() for part in (existing.reason, candidate.reason) if part.strip()]
            deduped: list[str] = []
            for reason in reasons:
                if reason not in deduped:
                    deduped.append(reason)
            existing.reason = ", ".join(deduped[:2])
    for candidate in database_candidates:
        merged.setdefault(candidate.entry.entry_id, candidate)
    results = list(merged.values())
    results.sort(key=lambda item: (item.source_rank, -item.score, item.entry.display_name.casefold(), item.entry.entry_id))
    return results[: max(1, limit)]


def _nav_candidates(
    ctx: CliContext,
    query: str,
    *,
    limit: int,
    include_context: bool,
    include_database: bool,
) -> list[NavigatorCandidate]:
    search_query = _effective_nav_query(query)
    workflow_candidates = _workflow_provider(ctx, search_query, limit=max(8, limit * 2))
    context_candidates = _context_provider(ctx, search_query, limit=max(6, limit)) if include_context else []
    database_candidates = _database_provider(ctx, search_query, limit=max(6, limit)) if include_database else []
    return _merge_nav_candidates(
        workflow_candidates,
        context_candidates,
        database_candidates,
        limit=limit,
    )


def _nav_sections(
    ctx: CliContext,
    query: str,
    *,
    limit: int,
    include_context: bool,
    include_database: bool,
    ai_state: NavigatorAIState | None = None,
) -> list[NavigatorSection]:
    search_query = _effective_nav_query(query)
    workflow_candidates = _workflow_provider(ctx, search_query, limit=max(1, limit))
    context_candidates = _context_provider(ctx, search_query, limit=max(1, limit)) if include_context else []
    database_candidates = _database_provider(ctx, search_query, limit=max(1, limit)) if include_database else []
    heuristic_candidates = _merge_nav_candidates(context_candidates, [], database_candidates, limit=max(1, limit))
    ai_candidates: list[NavigatorCandidate] = []
    ai_empty_message = "Generating AI suggestion..."
    if ai_state is not None:
        with ai_state.lock:
            if ai_state.request_text:
                if ai_state.candidates:
                    ai_candidates = list(ai_state.candidates)
                if ai_state.busy:
                    ai_empty_message = ai_state.error_message or "Generating AI suggestions..."
                elif ai_state.error_message:
                    ai_empty_message = ai_state.error_message
                elif not ai_candidates:
                    ai_empty_message = "No AI suggestions returned."
    sections = [
        NavigatorSection("Heuristic/Deterministic recommendations", "heuristic", heuristic_candidates),
    ]
    if _ai_enabled(ctx):
        sections.append(NavigatorSection("Ai recommendations (Synthetic/heuristic)", "ai", ai_candidates, empty_message=ai_empty_message))
    sections.append(NavigatorSection("Workflow recommendations", "workflow", workflow_candidates))
    return sections
