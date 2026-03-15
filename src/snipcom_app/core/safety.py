from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandRisk:
    risky: bool
    reasons: tuple[str, ...]


RISK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|[\s;&|])rm\s+-rf?\s+/(?:\s|$)"), "Removes files from root using rm -rf /."),
    (re.compile(r"(^|[\s;&|])mkfs(\.[a-z0-9_-]+)?\s+", re.IGNORECASE), "Formats a filesystem device (mkfs)."),
    (re.compile(r"(^|[\s;&|])dd\s+.*\bof=/dev/", re.IGNORECASE), "Writes raw bytes directly to a block device (dd)."),
    (re.compile(r"(^|[\s;&|])(reboot|shutdown|poweroff|halt)\b", re.IGNORECASE), "Requests system shutdown/reboot."),
    (re.compile(r"(^|[\s;&|])chown\s+-R\s+root\b", re.IGNORECASE), "Recursively changes ownership to root."),
    (re.compile(r"(^|[\s;&|])chmod\s+-R\s+777\b", re.IGNORECASE), "Recursively grants world write/execute permissions."),
    (re.compile(r"(^|[\s;&|]):\(\)\s*\{\s*:\|:\s*&\s*\};\s*:"), "Contains a fork bomb pattern."),
)


def evaluate_command_risk(command: str, *, dangerous_flag: bool = False) -> CommandRisk:
    reasons: list[str] = []
    if dangerous_flag:
        reasons.append("Entry is marked as dangerous.")

    cleaned_command = command.strip()
    if cleaned_command:
        for pattern, reason in RISK_PATTERNS:
            if pattern.search(cleaned_command):
                reasons.append(reason)

    return CommandRisk(risky=bool(reasons), reasons=tuple(reasons))

