"""Local AI provider and normalization layer.

Read this header first: keep reading here only when the change is about Ollama,
provider calls, prompt sanitation, or raw AI request/response handling.
Workflow-specific AI behavior lives elsewhere.

This file owns:
- provider connectivity checks
- request/response normalization
- low-level prompt helpers

Related files:
- `ai_controller.py`: app-specific AI behavior, ranking, and context building
- `terminal_controller.py`: terminal-side AI trigger flow
- `search_controller.py`: quick-search AI trigger flow
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import Any
from urllib import error, request


DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AISuggestionContext:
    user_request: str
    last_terminal_input: str
    last_terminal_output: str
    primary_tool: str
    recent_searches: tuple[str, ...]
    related_commands: tuple[str, ...]


@dataclass(frozen=True)
class AIConnectionStatus:
    ok: bool
    message: str
    available_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class AISuggestionResult:
    command: str
    provider: str
    model: str
    raw_text: str
    used_context: dict[str, Any]
    confidence_low: bool = False


def normalize_endpoint(endpoint: str) -> str:
    cleaned = endpoint.strip() or DEFAULT_OLLAMA_ENDPOINT
    return cleaned.rstrip("/")


def _json_request(url: str, payload: dict[str, Any] | None = None, *, timeout: int = 20) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    http_request = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ConnectionRefusedError):
            raise AIProviderError(
                f"Could not connect to Ollama at {url}. Start Ollama there or install it first."
            ) from exc
        raise AIProviderError(f"Could not reach Ollama at {url}: {reason}") from exc
    except json.JSONDecodeError as exc:
        raise AIProviderError("Ollama returned invalid JSON.") from exc


def check_ollama_status(endpoint: str, model: str, *, timeout: int = 10) -> AIConnectionStatus:
    normalized_endpoint = normalize_endpoint(endpoint)
    payload = _json_request(f"{normalized_endpoint}/api/tags", timeout=timeout)
    models = payload.get("models", [])
    available_models = tuple(
        sorted(
            {
                str(item.get("model", "")).strip()
                for item in models
                if isinstance(item, dict) and str(item.get("model", "")).strip()
            }
        )
    )
    requested_model = model.strip()
    if not requested_model:
        return AIConnectionStatus(True, "Ollama is reachable. No model selected yet.", available_models)
    if requested_model in available_models:
        return AIConnectionStatus(True, f"Ollama is reachable and {requested_model} is available.", available_models)
    return AIConnectionStatus(
        False,
        f"Ollama is reachable, but {requested_model} is not installed there.",
        available_models,
    )


def build_generation_prompt(context: AISuggestionContext) -> str:
    request_overrides_terminal = user_request_overrides_terminal_context(context)
    sections = [
        "You generate exactly one likely next shell command.",
        "Target environment: Fedora Linux shell.",
        "Return only the command.",
        "Do not return explanations, bullets, markdown, or code fences.",
        "Do not wrap the command in apostrophes, quotation marks, or backticks unless they are required as part of the command itself.",
        "Do not use placeholders such as /path/to/..., <name>, filename, your_repo, example, or toplevel_directory.",
        "If you do not know an exact path or value, choose a concrete discovery command instead of inventing a placeholder.",
        "The command must be executable as written right now.",
        "Prefer a safe inspection or navigation command unless the user explicitly asks for something destructive.",
        "If there is terminal context, use it to infer the most likely next step.",
        "Stay in the same tool family as the last terminal input unless the user request clearly changes topic.",
        "Do not repeat the last terminal command exactly.",
        "Do not return a minor flag or formatting variation of the last terminal command unless the user explicitly asks for that.",
        "If the user request is generic or short, infer a useful next inspection step from the last command and its output.",
    ]
    if context.primary_tool.strip():
        sections.extend(["", "Current tool family anchor:", context.primary_tool.strip()])
    if context.user_request.strip():
        sections.extend(["", "User request:", context.user_request.strip()])
    if context.last_terminal_input.strip():
        sections.extend(["", "Last terminal input:", context.last_terminal_input.strip()])
        lowered_last_input = context.last_terminal_input.strip().casefold()
        if request_overrides_terminal:
            sections.extend(
                [
                    "",
                    "The user request changes topic from the last terminal command.",
                    "Follow the user request rather than the previous terminal family.",
                ]
            )
        elif lowered_last_input == "rpm -qa":
            sections.extend(
                [
                    "",
                    "Special rule for 'rpm -qa': prefer a useful follow-up like 'rpm -qi <real package from output>' or 'rpm -qa | less'.",
                    "Do not jump to unrelated rpm subcommands unless the user asked for that.",
                ]
            )
        elif lowered_last_input == "ls":
            sections.extend(
                [
                    "",
                    "Special rule for bare 'ls': do not suggest another ls variant.",
                    "Prefer a different concrete follow-up such as 'pwd' or another non-trivial inspection command.",
                ]
            )
    if context.last_terminal_output.strip():
        trimmed_output = context.last_terminal_output.strip()
        if len(trimmed_output) > 3000:
            trimmed_output = trimmed_output[:3000].rstrip() + "\n[truncated]"
        sections.extend(["", "Last terminal output:", trimmed_output])
    if context.recent_searches:
        sections.extend(["", "Recent app searches:"])
        sections.extend(f"- {query}" for query in context.recent_searches if query.strip())
    if context.related_commands:
        sections.extend(["", "Related commands seen in the app database:"])
        sections.extend(f"- {command}" for command in context.related_commands if command.strip())
    sections.extend(["", "Output:", "One shell command only."])
    return "\n".join(sections)


def build_repair_prompt(context: AISuggestionContext, rejected_command: str) -> str:
    sections = [
        "Your previous answer was not acceptable because it used placeholders or a non-concrete command.",
        f"Rejected answer: {rejected_command}",
        "Generate exactly one real shell command for Fedora Linux.",
        "Return only the command.",
        "Do not wrap the command in apostrophes, quotation marks, or backticks unless they are required as part of the command itself.",
        "No placeholders, no angle brackets, no example paths, no prose.",
        "If you do not know an exact path, return a concrete discovery command that helps the user find it.",
    ]
    if context.user_request.strip():
        sections.extend(["", "User request:", context.user_request.strip()])
    if context.primary_tool.strip():
        sections.extend(["", "Current tool family anchor:", context.primary_tool.strip()])
    if context.last_terminal_input.strip():
        sections.extend(["", "Last terminal input:", context.last_terminal_input.strip()])
    if context.last_terminal_output.strip():
        trimmed_output = context.last_terminal_output.strip()
        if len(trimmed_output) > 2000:
            trimmed_output = trimmed_output[:2000].rstrip() + "\n[truncated]"
        sections.extend(["", "Last terminal output:", trimmed_output])
    if context.related_commands:
        sections.extend(["", "Related commands:"])
        sections.extend(f"- {command}" for command in context.related_commands[:6] if command.strip())
    sections.extend(["", "Output:", "One executable shell command only."])
    return "\n".join(sections)


def build_repeat_repair_prompt(context: AISuggestionContext, rejected_command: str) -> str:
    sections = [
        "Your previous answer was not acceptable because it repeated the last terminal command or only made a trivial variation.",
        f"Rejected answer: {rejected_command}",
        "Generate exactly one different Fedora Linux shell command.",
        "Return only the command.",
        "Do not wrap the command in apostrophes, quotation marks, or backticks unless they are required as part of the command itself.",
        "Do not repeat the last command.",
        "Do not make a minor flag-order or formatting change to the last command.",
        "Choose a concrete next inspection, filtering, navigation, or detail command that naturally follows from the context.",
        "If the last command produced a long list, prefer a useful follow-up such as narrowing, paging, or inspecting one likely next item.",
    ]
    if context.user_request.strip():
        sections.extend(["", "User request:", context.user_request.strip()])
    if context.primary_tool.strip():
        sections.extend(["", "Current tool family anchor:", context.primary_tool.strip()])
    if context.last_terminal_input.strip():
        sections.extend(["", "Last terminal input:", context.last_terminal_input.strip()])
    if context.last_terminal_output.strip():
        trimmed_output = context.last_terminal_output.strip()
        if len(trimmed_output) > 2000:
            trimmed_output = trimmed_output[:2000].rstrip() + "\n[truncated]"
        sections.extend(["", "Last terminal output:", trimmed_output])
    if context.related_commands:
        sections.extend(["", "Related commands:"])
        sections.extend(f"- {command}" for command in context.related_commands[:6] if command.strip())
    sections.extend(["", "Output:", "One executable shell command only."])
    return "\n".join(sections)


def sanitize_generated_command(raw_text: str) -> tuple[str, bool]:
    cleaned = raw_text.replace("\r\n", "\n").strip()
    if not cleaned:
        return "", True
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    filtered_lines: list[str] = []
    for line in lines:
        if line.startswith("```"):
            continue
        if line.startswith("$ "):
            line = line[2:].strip()
        lowered = line.casefold()
        for prefix in ("command:", "suggested command:", "shell command:", "bash:"):
            if lowered.startswith(prefix):
                line = line[len(prefix) :].strip()
                lowered = line.casefold()
                break
        if not line:
            continue
        filtered_lines.append(line)
    if not filtered_lines:
        return "", True
    first_line = filtered_lines[0]
    if len(first_line) >= 2:
        paired_wrappers = (("`", "`"), ("'", "'"), ('"', '"'))
        for left, right in paired_wrappers:
            if first_line.startswith(left) and first_line.endswith(right):
                first_line = first_line[1:-1].strip()
                break
    confidence_low = len(filtered_lines) > 1 or first_line != cleaned
    return first_line, confidence_low


def has_obvious_placeholder(command: str) -> bool:
    lowered = command.casefold()
    placeholder_markers = (
        "/path/to",
        "<",
        ">",
        "filename",
        "example",
        "your_repo",
        "toplevel_directory",
        "your-directory",
        "your_file",
    )
    return any(marker in lowered for marker in placeholder_markers)


def _normalized_command_tokens(command: str) -> list[str]:
    cleaned = command.strip()
    if not cleaned:
        return []
    try:
        tokens = shlex.split(cleaned)
    except ValueError:
        tokens = cleaned.split()
    normalized: list[str] = []
    for token in tokens:
        lowered = token.casefold()
        if lowered in {"sudo", "env", "command", "builtin", "nohup", "time"}:
            continue
        normalized.append(token)
    return normalized


def _flag_signature(tokens: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    flags: list[str] = []
    args: list[str] = []
    for token in tokens[1:]:
        if token.startswith("-") and len(token) > 1:
            if token.startswith("--"):
                flags.append(token)
            else:
                flags.extend(f"-{flag}" for flag in token[1:])
        else:
            args.append(token)
    return tuple(sorted(flags)), tuple(args)


def is_trivial_repeat(command: str, last_command: str) -> bool:
    suggested_tokens = _normalized_command_tokens(command)
    previous_tokens = _normalized_command_tokens(last_command)
    if not suggested_tokens or not previous_tokens:
        return False
    suggested_joined = " ".join(suggested_tokens).casefold()
    previous_joined = " ".join(previous_tokens).casefold()
    if suggested_joined == previous_joined:
        return True
    if suggested_tokens[0].casefold() != previous_tokens[0].casefold():
        return False
    suggested_flags, suggested_args = _flag_signature(suggested_tokens)
    previous_flags, previous_args = _flag_signature(previous_tokens)
    if suggested_args == previous_args:
        if suggested_flags == previous_flags:
            return True
        if set(suggested_flags).issuperset(previous_flags) or set(previous_flags).issuperset(suggested_flags):
            return True
    if suggested_joined.startswith(previous_joined) or previous_joined.startswith(suggested_joined):
        return True
    return False


def _extract_last_nonempty_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _command_head(command: str) -> str:
    tokens = _normalized_command_tokens(command)
    return tokens[0].casefold() if tokens else ""


def user_request_overrides_terminal_context(context: AISuggestionContext) -> bool:
    terminal_head = _command_head(context.last_terminal_input)
    if not context.user_request.strip() or not context.primary_tool.strip() or not terminal_head:
        return False
    return context.primary_tool.casefold() != terminal_head


def _looks_like_path(value: str) -> bool:
    return value.startswith(("/", "./", "../", "~/"))


def _looks_like_package_name(value: str) -> bool:
    if not value or _looks_like_path(value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+]+)+", value))


def is_unhelpful_for_context(command: str, context: AISuggestionContext) -> bool:
    if user_request_overrides_terminal_context(context):
        return False
    last_input = context.last_terminal_input.strip().casefold()
    suggested = command.strip()
    if not suggested:
        return True
    if last_input == "rpm -qa":
        tokens = _normalized_command_tokens(suggested)
        if len(tokens) >= 3 and tokens[0].casefold() == "rpm" and tokens[1].casefold() == "-qf":
            target = tokens[2]
            if _looks_like_package_name(target):
                return True
    return False


def deterministic_fallback_command(context: AISuggestionContext) -> str:
    if user_request_overrides_terminal_context(context):
        return ""
    last_input = context.last_terminal_input.strip()
    lowered_last_input = last_input.casefold()
    if not last_input:
        return ""
    if lowered_last_input == "rpm -qa":
        candidate = _extract_last_nonempty_line(context.last_terminal_output)
        if candidate and not re.search(r"\s", candidate):
            return f"rpm -qi {shlex.quote(candidate)}"
        return "rpm -qa | less"
    if lowered_last_input == "ls":
        return "pwd"
    if lowered_last_input.startswith("git status"):
        return "git diff --stat"
    if lowered_last_input.startswith("git log"):
        return "git show --stat"
    return ""


def _generate_ollama_text(
    endpoint: str,
    model: str,
    prompt: str,
    *,
    timeout: int,
) -> str:
    normalized_endpoint = normalize_endpoint(endpoint)
    payload = {
        "model": model.strip(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
        },
    }
    response_payload = _json_request(f"{normalized_endpoint}/api/generate", payload, timeout=timeout)
    return str(response_payload.get("response", "")).strip()


def generate_ollama_command(
    endpoint: str,
    model: str,
    context: AISuggestionContext,
    *,
    timeout: int = 35,
) -> AISuggestionResult:
    prompt = build_generation_prompt(context)
    raw_text = _generate_ollama_text(endpoint, model, prompt, timeout=timeout)
    command, confidence_low = sanitize_generated_command(raw_text)
    if not command:
        raise AIProviderError("The model did not return a usable command.")
    if has_obvious_placeholder(command):
        repaired_raw_text = _generate_ollama_text(
            endpoint,
            model,
            build_repair_prompt(context, command),
            timeout=timeout,
        )
        repaired_command, repaired_confidence_low = sanitize_generated_command(repaired_raw_text)
        if repaired_command and not has_obvious_placeholder(repaired_command):
            raw_text = repaired_raw_text
            command = repaired_command
            confidence_low = True
    if context.last_terminal_input.strip() and is_trivial_repeat(command, context.last_terminal_input):
        repaired_raw_text = _generate_ollama_text(
            endpoint,
            model,
            build_repeat_repair_prompt(context, command),
            timeout=timeout,
        )
        repaired_command, repaired_confidence_low = sanitize_generated_command(repaired_raw_text)
        if repaired_command and not has_obvious_placeholder(repaired_command):
            raw_text = repaired_raw_text
            command = repaired_command
            confidence_low = True or repaired_confidence_low
    if is_unhelpful_for_context(command, context):
        fallback_command = deterministic_fallback_command(context)
        if fallback_command:
            command = fallback_command
            raw_text = fallback_command
            confidence_low = True
        else:
            raise AIProviderError("The model returned a low-value command for the current context.")
    if context.last_terminal_input.strip() and is_trivial_repeat(command, context.last_terminal_input):
        fallback_command = deterministic_fallback_command(context)
        if fallback_command:
            command = fallback_command
            raw_text = fallback_command
            confidence_low = True
        else:
            raise AIProviderError("The model repeated the previous command instead of producing a useful next step.")
    return AISuggestionResult(
        command=command,
        provider="ollama",
        model=model.strip(),
        raw_text=raw_text,
        used_context={
            "user_request": context.user_request,
            "last_terminal_input": context.last_terminal_input,
            "last_terminal_output": context.last_terminal_output,
            "primary_tool": context.primary_tool,
            "recent_searches": list(context.recent_searches),
            "related_commands": list(context.related_commands),
        },
        confidence_low=confidence_low,
    )
