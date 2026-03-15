from __future__ import annotations

import threading

from ..ai.ai import AIProviderError, generate_ollama_commands_multi
from .cli_context import CliContext
from .nav_providers import (
    NavigatorAIState,
    NavigatorCandidate,
    _ai_enabled,
    _ai_endpoint,
    _ai_model,
    _ai_provider,
    _ai_timeout_seconds,
    _build_cli_ai_context,
    _natural_request_text,
    _synthetic_entry,
)


def _generate_cli_ai_candidates(ctx: CliContext, request_text: str, n: int = 5) -> tuple[list[NavigatorCandidate], str]:
    cleaned_request = request_text.strip()
    if not cleaned_request:
        return [], ""
    if not _ai_enabled(ctx):
        return [], "AI is disabled. Enable it in Settings > Options > AI."
    if _ai_provider(ctx) != "ollama":
        return [], f"Unsupported AI provider: {_ai_provider(ctx)}"
    try:
        context = _build_cli_ai_context(ctx, cleaned_request)
        suggestions = generate_ollama_commands_multi(
            _ai_endpoint(ctx),
            _ai_model(ctx),
            context,
            n=n,
            timeout=_ai_timeout_seconds(ctx),
        )
    except (AIProviderError, KeyError, OSError, ValueError) as exc:
        return [], str(exc)
    if not suggestions:
        return [], "The model did not return usable commands."
    candidates = []
    for suggestion in suggestions:
        command = suggestion.command.strip()
        if not command:
            continue
        candidates.append(NavigatorCandidate(
            entry=_synthetic_entry(
                command,
                entry_id=f"synthetic:ai:{abs(hash((cleaned_request.casefold(), command)))}",
                snip_type="family_command",
                family_key=context.primary_tool or "ai",
                source_kind=suggestion.provider,
            ),
            source_label="ai",
            source_rank=2,
            score=100,
            reason=f"AI via {suggestion.model}",
            body=command,
        ))
    return candidates, ""


def _generate_cli_ai_candidate(ctx: CliContext, request_text: str) -> tuple[NavigatorCandidate | None, str]:
    """Single-result version kept for use by cli_handlers_advanced.py nat command."""
    candidates, error = _generate_cli_ai_candidates(ctx, request_text, n=1)
    return (candidates[0] if candidates else None), error


def _clear_ai_state(ai_state: NavigatorAIState) -> None:
    with ai_state.lock:
        ai_state.request_text = ""
        ai_state.busy = False
        ai_state.error_message = ""
        ai_state.candidates = []
        ai_state.generation_id += 1


def _refresh_ai_state(ctx: CliContext, buffer_text: str, ai_state: NavigatorAIState) -> None:
    nat_text = _natural_request_text(buffer_text)
    request_text = nat_text if nat_text else buffer_text.strip()
    if not request_text:
        if ai_state.request_text or ai_state.busy or ai_state.error_message or ai_state.candidates:
            _clear_ai_state(ai_state)
        return
    if not _ai_enabled(ctx):
        with ai_state.lock:
            ai_state.request_text = request_text
            ai_state.busy = False
            ai_state.error_message = "AI is disabled. Enable it in Settings > Options > AI."
            ai_state.candidates = []
        return
    if _ai_provider(ctx) != "ollama":
        with ai_state.lock:
            ai_state.request_text = request_text
            ai_state.busy = False
            ai_state.error_message = f"Unsupported AI provider: {_ai_provider(ctx)}"
            ai_state.candidates = []
        return
    with ai_state.lock:
        if ai_state.request_text.casefold() == request_text.casefold() and (ai_state.busy or ai_state.candidates or ai_state.error_message):
            return
        ai_state.request_text = request_text
        ai_state.busy = True
        ai_state.error_message = "Generating AI suggestions..."
        ai_state.candidates = []
        ai_state.generation_id += 1
        generation_id = ai_state.generation_id

    def _worker() -> None:
        candidates, error_message = _generate_cli_ai_candidates(ctx, request_text, n=5)
        with ai_state.lock:
            if generation_id != ai_state.generation_id or ai_state.request_text.casefold() != request_text.casefold():
                return
            ai_state.busy = False
            ai_state.error_message = error_message
            ai_state.candidates = candidates

    threading.Thread(target=_worker, daemon=True).start()
