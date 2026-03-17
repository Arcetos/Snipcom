from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from ...ai.ai import AIProviderError, AISuggestionContext, AISuggestionResult, check_ollama_status, deterministic_fallback_command
from ...ai.ai_shared import ai_anchor_terms, primary_tool_for_ai

if TYPE_CHECKING:
    from ..main_window import NoteCopyPaster
    from ...core.repository import SnipcomEntry


class AiController:
    def __init__(self, window: "NoteCopyPaster", *, terminal_suggestion_count: int) -> None:
        self.window = window
        self.terminal_suggestion_count = terminal_suggestion_count

    def primary_tool_for_ai(self, last_terminal_input: str, user_request: str) -> str:
        return primary_tool_for_ai(
            self.window.repository.catalog_entries(include_active_commands=True),
            last_terminal_input,
            user_request,
        )

    def ai_anchor_terms(self, *values: str) -> list[str]:
        return ai_anchor_terms(*values)

    def filter_recent_searches_for_ai(self, last_terminal_input: str, user_request: str) -> tuple[str, ...]:
        searches = tuple(query for query in self.window.recent_search_queries if query.strip())
        if not searches:
            return ()
        primary_terms = set(self.ai_anchor_terms(last_terminal_input, user_request))
        if not primary_terms:
            return searches[:2]
        filtered = [query for query in searches if any(term in query.casefold() for term in primary_terms)]
        return tuple(filtered[:2])

    def collect_related_commands_for_ai(
        self,
        last_terminal_input: str,
        user_request: str,
        primary_tool: str,
        *,
        include_terminal_context: bool = True,
    ) -> list[str]:
        window = self.window
        related: list[str] = []
        candidate_ids: list[int] = []
        if include_terminal_context:
            terminal_label = window.selected_linked_terminal_label()
            terminal_runtime = str(window.current_linked_terminal_dir or "")
            latest_command_id = (
                window.repository.command_store.latest_terminal_command_id(
                    terminal_label, terminal_runtime=terminal_runtime
                )
                if terminal_label or terminal_runtime
                else None
            )
            if latest_command_id is not None:
                candidate_ids.extend(window.repository.command_store.related_command_ids(latest_command_id, limit=6))
        query_terms: list[str] = []
        if last_terminal_input.strip():
            query_terms.append(last_terminal_input.strip())
        if user_request.strip():
            query_terms.append(user_request.strip())
        query_terms.extend(self.filter_recent_searches_for_ai(last_terminal_input, user_request))
        seen_ids: set[int] = set(candidate_ids)
        token_terms = self.ai_anchor_terms(*query_terms[:3])
        for query in query_terms[:3]:
            lowered_query = query.casefold()
            for entry in window.repository.catalog_entries(include_active_commands=True):
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
            entry = window.repository.entry_from_id(
                window.repository.command_entry_id(command_id),
                window.tags,
                window.snip_types,
            )
            if entry is not None:
                related.append(entry.display_name)
        return related

    def _read_directory_files(self, cwd: str) -> tuple[str, ...]:
        if not cwd:
            return ()
        try:
            p = Path(cwd)
            if not p.is_dir():
                return ()
            entries = []
            for entry in p.iterdir():
                name = entry.name
                if name.startswith("."):
                    continue
                entries.append(name + "/" if entry.is_dir() else name)
            return tuple(sorted(entries)[:50])
        except OSError:
            return ()

    def build_ai_suggestion_context(self, user_request: str, *, include_terminal_context: bool = True) -> AISuggestionContext:
        window = self.window
        last_terminal_input = window.terminal_controller.latest_terminal_input() if include_terminal_context else ""
        last_terminal_output = window.terminal_controller.latest_terminal_output_quiet() if include_terminal_context else ""
        current_directory = window.terminal_controller.latest_terminal_cwd() if include_terminal_context else ""
        directory_files = self._read_directory_files(current_directory)
        primary_tool = self.primary_tool_for_ai(last_terminal_input, user_request)
        filtered_recent_searches = self.filter_recent_searches_for_ai(last_terminal_input, user_request)
        return AISuggestionContext(
            user_request=user_request.strip(),
            last_terminal_input=last_terminal_input,
            last_terminal_output=last_terminal_output,
            primary_tool=primary_tool,
            recent_searches=filtered_recent_searches,
            related_commands=tuple(
                self.collect_related_commands_for_ai(
                    last_terminal_input,
                    user_request,
                    primary_tool,
                    include_terminal_context=include_terminal_context,
                )
            ),
            current_directory=current_directory,
            directory_files=directory_files,
        )

    def format_terminal_suggestions_overlay(self, suggestions: list[str]) -> str:
        lines = [""] * self.terminal_suggestion_count
        slot_rows = {1: 2, 2: 1, 3: 3, 4: 0, 5: 4}
        slot_indents = {1: 0, 2: 2, 3: 4, 4: 6, 5: 6}
        for index, command in enumerate(suggestions[: self.terminal_suggestion_count], start=1):
            row = slot_rows.get(index, min(index - 1, self.terminal_suggestion_count - 1))
            indent = slot_indents.get(index, 10)
            lines[row] = f"{' ' * indent}{index}. {command}"
        return "\n".join(lines)

    def inline_ai_suggestion_matches_current_settings(self, suggestion: AISuggestionResult | None) -> bool:
        if suggestion is None:
            return False
        if suggestion.provider != self.window.ai_provider():
            return False
        if suggestion.model != self.window.ai_model():
            return False
        return True

    def inline_suggestion_matches_request(
        self,
        suggestion: AISuggestionResult | None,
        *,
        request_text: str,
        cached_request: str,
    ) -> bool:
        return (
            suggestion is not None
            and self.inline_ai_suggestion_matches_current_settings(suggestion)
            and cached_request.casefold() == request_text.casefold()
        )

    def generate_inline_ai_suggestion(
        self, user_request: str, *, include_terminal_context: bool = True
    ) -> tuple[AISuggestionResult | None, str]:
        # Inline terminal suggestions are heuristic-only — no catalog scan, no AI call.
        window = self.window
        last_input = window.terminal_controller.latest_terminal_input() if include_terminal_context else ""
        last_output = window.terminal_controller.latest_terminal_output_quiet() if include_terminal_context else ""
        cwd = window.terminal_controller.latest_terminal_cwd() if include_terminal_context else ""
        context = AISuggestionContext(
            user_request=user_request.strip(),
            last_terminal_input=last_input,
            last_terminal_output=last_output,
            primary_tool="",
            recent_searches=(),
            related_commands=(),
            current_directory=cwd,
            directory_files=(),
        )
        fallback = deterministic_fallback_command(context)
        if fallback:
            return AISuggestionResult(
                command=fallback,
                provider="deterministic",
                model="",
                raw_text=fallback,
                used_context={"last_terminal_input": last_input},
                confidence_low=False,
            ), ""
        return None, ""

    def terminal_family_candidates(self, primary_tool: str) -> list[str]:
        candidates: list[str] = []
        if not primary_tool:
            return candidates
        matching_families = self.terminal_matching_families(primary_tool)
        for entry in self.window.repository.catalog_entries(include_active_commands=True):
            if not entry.is_command or entry.dangerous:
                continue
            entry_family = entry.family_key.strip()
            entry_name = entry.display_name.strip()
            if not entry_name:
                continue
            if (
                entry_family in matching_families
                or primary_tool in entry_name.casefold()
                or primary_tool in entry.tag_text.casefold()
            ):
                if "<" in entry_name or ">" in entry_name or "\\" in entry_name:
                    continue
                candidates.append(entry_name)
        return candidates

    def terminal_matching_families(self, primary_tool: str) -> set[str]:
        if not primary_tool:
            return set()
        family_aliases = {
            "rpm": {"packaging"},
            "dnf": {"packaging"},
            "yum": {"packaging"},
            "apt": {"packaging"},
            "apt-get": {"packaging"},
            "apt-cache": {"packaging"},
            "dpkg": {"packaging"},
            "pacman": {"packaging"},
            "zypper": {"packaging"},
            "apk": {"packaging"},
            "snap": {"packaging"},
            "flatpak": {"packaging"},
            "ls": {"Shell Directories", "Shell Files", "Shell System"},
            "pwd": {"Shell Directories", "Shell Files", "Shell System"},
            "find": {"Shell Directories", "Shell Files"},
            "journalctl": {"journalctl"},
            "git": {"git"},
        }
        return {primary_tool, *family_aliases.get(primary_tool, set())}

    def terminal_entry_matches_tool(self, entry: "SnipcomEntry", primary_tool: str) -> bool:
        if not primary_tool:
            return True
        matching_families = self.terminal_matching_families(primary_tool)
        entry_name = entry.display_name.casefold()
        entry_family = entry.family_key.casefold()
        entry_tags = entry.tag_text.casefold()
        return (
            entry.family_key in matching_families
            or primary_tool in entry_name
            or primary_tool in entry_family
            or primary_tool in entry_tags
        )

    def command_entry_for_terminal_command(self, command_text: str):
        cleaned = command_text.strip()
        if not cleaned:
            return None
        for entry in self.window.repository.catalog_entries(include_active_commands=True):
            if not entry.is_command or entry.command_id is None:
                continue
            if entry.display_name.strip() == cleaned:
                return entry
        return None

    def transition_based_terminal_suggestions(self, last_input: str) -> list[str]:
        window = self.window
        entry = self.command_entry_for_terminal_command(last_input)
        if entry is None or entry.command_id is None:
            return []
        primary_tool = self.primary_tool_for_ai(last_input, "")
        terminal_label = window.selected_linked_terminal_label()
        suggestions: list[str] = []
        weighted_ids = window.repository.command_store.transition_weights(entry.command_id, terminal_label=terminal_label)
        ranked_ids = [command_id for command_id, _weight in sorted(weighted_ids.items(), key=lambda item: (-item[1], item[0]))]
        for command_id in ranked_ids:
            related_entry = window.repository.entry_from_id(
                window.repository.command_entry_id(command_id),
                window.tags,
                window.snip_types,
            )
            if related_entry is None or not related_entry.is_command or related_entry.dangerous:
                continue
            if not self.terminal_entry_matches_tool(related_entry, primary_tool):
                continue
            suggestions.append(related_entry.display_name)
            if len(suggestions) >= self.terminal_suggestion_count:
                break
        return suggestions

    def extract_package_candidates(self, output: str) -> list[str]:
        packages: list[str] = []
        for line in output.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if re.fullmatch(r"[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+]+)+", candidate):
                packages.append(candidate)
        return packages[-5:]

    def extract_paths_from_output(self, output: str) -> list[str]:
        paths: list[str] = []
        for line in output.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith(("/", "./", "../", "~/")):
                paths.append(candidate)
        return paths[-5:]

    def extract_git_branch_from_output(self, output: str) -> str:
        for line in output.splitlines():
            match = re.match(r"On branch\s+(.+)$", line.strip())
            if match:
                return match.group(1).strip()
        return ""

    def git_status_based_suggestions(self, output: str) -> list[str]:
        lowered = output.casefold()
        suggestions: list[str] = []
        if "changes to be committed" in lowered:
            suggestions.extend(['git commit -m "Describe the change"', "git diff --cached --stat", "git status"])
        elif "changes not staged for commit" in lowered or "untracked files" in lowered:
            suggestions.extend(["git add -A", "git diff --stat", "git status"])
        elif "nothing to commit" in lowered and "working tree clean" in lowered:
            suggestions.extend(["git log --all --decorate --oneline --graph", "git pull --ff-only", "git branch --show-current"])
        branch = self.extract_git_branch_from_output(output)
        if branch and "git branch --show-current" not in suggestions:
            suggestions.append("git branch --show-current")
        return suggestions[: self.terminal_suggestion_count]

    def rpm_query_based_suggestions(self, last_input: str, output: str) -> list[str]:
        suggestions: list[str] = []
        lowered = last_input.casefold()
        if lowered == "rpm -qa":
            packages = self.extract_package_candidates(output)
            if packages:
                package = packages[-1]
                suggestions.extend([f"rpm -qi {package}", f"rpm -ql {package}", "rpm -qa | less"])
            else:
                suggestions.extend(["rpm -qa | less", "rpm -q --last", "dnf list installed"])
        elif lowered.startswith("rpm -qi "):
            package = last_input.split(maxsplit=2)[-1].strip()
            if package:
                suggestions.extend([f"rpm -ql {package}", f"rpm -q --whatrequires {package}", "rpm -q --last"])
        return suggestions[: self.terminal_suggestion_count]

    def apt_query_based_suggestions(self, last_input: str, output: str) -> list[str]:
        suggestions: list[str] = []
        lowered = last_input.casefold()
        if lowered in {"apt list --installed", "dpkg -l"}:
            packages = self.extract_package_candidates(output)
            if packages:
                package = packages[-1]
                suggestions.extend([f"apt show {package}", f"dpkg -L {package}", "apt list --installed | less"])
            else:
                suggestions.extend(["apt list --installed | less", "apt search ", "dpkg -l | less"])
        elif lowered.startswith("apt show ") or lowered.startswith("apt-cache show "):
            package = last_input.split(maxsplit=2)[-1].strip()
            if package:
                suggestions.extend([f"dpkg -L {package}", f"apt-cache rdepends {package}", "apt list --installed"])
        elif lowered.startswith("dpkg -l ") or lowered.startswith("dpkg -s "):
            package = last_input.split(maxsplit=2)[-1].strip()
            if package:
                suggestions.extend([f"dpkg -L {package}", f"apt show {package}", "apt list --installed"])
        return suggestions[: self.terminal_suggestion_count]

    def pacman_query_based_suggestions(self, last_input: str, output: str) -> list[str]:
        suggestions: list[str] = []
        lowered = last_input.casefold()
        if lowered in {"pacman -q", "pacman -qs", "pacman -qe"}:
            packages = self.extract_package_candidates(output)
            if packages:
                package = packages[-1]
                suggestions.extend([f"pacman -Qi {package}", f"pacman -Ql {package}", "pacman -Qs | less"])
            else:
                suggestions.extend(["pacman -Qs | less", "pacman -Ss ", "pacman -Qu"])
        elif lowered.startswith("pacman -qi "):
            package = last_input.split(maxsplit=2)[-1].strip()
            if package:
                suggestions.extend([f"pacman -Ql {package}", f"pacman -Si {package}", "pacman -Qu"])
        return suggestions[: self.terminal_suggestion_count]

    def path_based_suggestions(self, last_input: str, output: str) -> list[str]:
        suggestions: list[str] = []
        paths = self.extract_paths_from_output(output)
        lowered = last_input.casefold()
        if lowered.startswith("find ") and paths:
            target = paths[-1]
            suggestions.extend([f"less {target}", f"xdg-open {target}", f"grep -n . {target}"])
        elif lowered in {"pwd", "ls", "ll"}:
            suggestions.extend(["find . -maxdepth 2 -type f", "pwd", "ll"])
        elif lowered.startswith("find "):
            suggestions.extend(["pwd", "ls", "ll"])
        return suggestions[: self.terminal_suggestion_count]

    def terminal_suggestion_matches_prefix(self, suggestion: str, typed_prefix: str) -> bool:
        cleaned_prefix = typed_prefix.strip().casefold()
        if not cleaned_prefix:
            return True
        candidate = suggestion.strip().casefold()
        if not candidate:
            return False
        if candidate.startswith(cleaned_prefix):
            return True
        tokens = [token for token in re.split(r"[^a-zA-Z0-9_.-]+", candidate) if token]
        return any(token.startswith(cleaned_prefix) for token in tokens)

    def passive_terminal_suggestions(self, typed_prefix: str = "") -> list[str]:
        window = self.window
        last_input = window.terminal_controller.latest_terminal_input().strip()
        last_output = window.terminal_controller.latest_terminal_output_quiet().strip()
        if not last_input:
            return []
        lowered = last_input.casefold()
        suggestions: list[str] = []

        if lowered.startswith("git status"):
            suggestions.extend(self.git_status_based_suggestions(last_output))
            suggestions.extend(["git add -A", "git log --all --decorate --oneline --graph", "git checkout <branch>"])
        elif lowered.startswith("git add"):
            suggestions.extend(['git commit -m "Describe the change"', "git status", "git log --all --decorate --oneline --graph"])
        elif lowered.startswith("git commit"):
            suggestions.extend(["git push -u <remote_name> <branch_name>", "git status", "git log"])
        elif lowered.startswith("git log"):
            suggestions.extend(["git status", "git add -A", "git checkout <branch>"])
        elif lowered.startswith("rpm -q"):
            suggestions.extend(self.rpm_query_based_suggestions(last_input, last_output))
        elif lowered.startswith("dnf list installed"):
            suggestions.extend(["dnf search <phrase>", "rpm -qa", "dnf provides <executable>"])
        elif lowered.startswith("dnf search"):
            suggestions.extend(["dnf install <package>", "dnf provides <executable>", "dnf list installed"])
        elif lowered.startswith("apt list") or lowered.startswith("dpkg -l"):
            suggestions.extend(self.apt_query_based_suggestions(last_input, last_output))
        elif lowered.startswith("apt search") or lowered.startswith("apt-cache search"):
            suggestions.extend(["apt install <package>", "apt show <package>", "apt list --installed"])
        elif lowered.startswith("apt show") or lowered.startswith("apt-cache show"):
            suggestions.extend(self.apt_query_based_suggestions(last_input, last_output))
        elif lowered.startswith("apt install") or lowered.startswith("apt-get install"):
            suggestions.extend(["apt show <package>", "dpkg -l | grep <name>", "apt list --installed"])
        elif lowered.startswith("pacman -q") or lowered.startswith("pacman -s"):
            suggestions.extend(self.pacman_query_based_suggestions(last_input, last_output))
        elif lowered.startswith("pacman -s ") or lowered.startswith("pacman -ss"):
            suggestions.extend(["pacman -S <package>", "pacman -Si <package>", "pacman -Qs"])
        elif lowered.startswith("zypper se") or lowered.startswith("zypper search"):
            suggestions.extend(["zypper install <package>", "zypper info <package>", "zypper lu"])
        elif lowered.startswith("zypper lu") or lowered.startswith("zypper list-updates"):
            suggestions.extend(["zypper up", "zypper patch", "zypper se --installed-only"])
        elif lowered == "ls":
            suggestions.extend(["pwd", "ll", "find . -maxdepth 2 -type f"])
        elif lowered == "pwd":
            suggestions.extend(["ls", "ll", "find . -maxdepth 2 -type f"])
        elif lowered.startswith("find "):
            suggestions.extend(self.path_based_suggestions(last_input, last_output))
        elif lowered.startswith("journalctl --list-boots"):
            suggestions.extend(["journalctl -b -p err", "journalctl -f", "journalctl -u dbus"])
        elif lowered.startswith("journalctl -b -p err"):
            suggestions.extend(["journalctl -f", "journalctl -u dbus", "journalctl _COMM=sshd"])
        else:
            suggestions.extend(self.path_based_suggestions(last_input, last_output))

        unique_suggestions: list[str] = []
        seen: set[str] = set()
        for suggestion in suggestions:
            cleaned = suggestion.strip()
            if not cleaned or "<" in cleaned or ">" in cleaned:
                continue
            lowered_suggestion = cleaned.casefold()
            if lowered_suggestion == lowered or lowered_suggestion in seen:
                continue
            seen.add(lowered_suggestion)
            unique_suggestions.append(cleaned)
            if len(unique_suggestions) >= 8:
                break

        cleaned_prefix = typed_prefix.strip()
        if cleaned_prefix:
            filtered = [item for item in unique_suggestions if self.terminal_suggestion_matches_prefix(item, cleaned_prefix)]
            return filtered[: self.terminal_suggestion_count]
        return unique_suggestions[: self.terminal_suggestion_count]

    def add_ai_generated_command_to_workflow(self, suggestion) -> None:
        window = self.window
        title = window.repository.unique_workflow_clone_title(suggestion.command, "family_command")
        record = window.repository.command_store.create_command(
            title,
            body=suggestion.command,
            snip_type="family_command",
            description="AI generated",
            source_kind="ai-generated",
            source_ref=suggestion.provider,
            source_license="",
            dangerous=False,
            extra={"model": suggestion.model, "used_context": suggestion.used_context},
        )
        window.push_undo({"type": "create_command", "command_id": record.command_id})
        window.refresh_workflow_views(refresh_store=True)
        window.show_status("Added AI-generated command to the workflow.")
        window.show_toast("Added AI-generated command to the workspace.")

    def check_ai_connection(self) -> tuple[bool, str]:
        window = self.window
        if window.ai_provider() != "ollama":
            return False, "Only Ollama is supported in this build."
        try:
            status = check_ollama_status(
                window.ai_endpoint(),
                window.ai_model(),
                timeout=window.ai_timeout_seconds(),
            )
        except AIProviderError as exc:
            return False, str(exc)
        return status.ok, status.message

