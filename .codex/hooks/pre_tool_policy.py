#!/usr/bin/env python3
"""Reject clearly unsafe local operations before Codex runs a tool."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


PRIVATE_PATH = re.compile(
    r"(?:^|[\s'\"=/])(?:\.env(?!\.example(?:\b|/))(?:\.[\w-]+)?|"
    r"data(?:/|\b)|logs(?:/|\b)|media(?:/|\b)|backups?(?:/|\b)|"
    r"[^\s'\"]+\.(?:session|session-journal))(?:$|[\s'\"/])",
    re.IGNORECASE,
)
DESTRUCTIVE = re.compile(
    r"\bgit\s+(?:reset\s+--hard|clean\b[^\n]*(?:-f|--force)|"
    r"checkout\s+--|restore\b[^\n]*--source|push\b[^\n]*(?:-f|--force)|"
    r"branch\s+-D|tag\s+-d)\b|"
    r"\brm\s+(?:-[A-Za-z]*[rf]|--(?:recursive|force))\b|"
    r"\b(?:shred|wipefs|mkfs)\b|\bfind\b[^\n]*\s-delete\b",
    re.IGNORECASE,
)
LIVE_SQLITE = re.compile(r"\bsqlite3\b[^\n]*(?:data/|telegram\.sqlite)", re.IGNORECASE)
BARE_ENV = re.compile(r"(?<![./\w-])(?:python3?|pip3?|uv)(?![\w-])")


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def text_from(event: dict[str, Any]) -> str:
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("command") or tool_input.get("patch") or "")


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    command = text_from(event)
    if not command:
        return
    if PRIVATE_PATH.search(command):
        deny(
            "Protected private path detected. Do not inspect or modify secrets, "
            "archives, Telegram sessions, logs, media, or backups through Codex."
        )
        return
    if LIVE_SQLITE.search(command):
        deny(
            "Direct access to the live SQLite archive is blocked. Use make db-check "
            "for read-only diagnostics or obtain explicit approval for a backup workflow."
        )
        return
    if DESTRUCTIVE.search(command):
        deny(
            "Destructive Git/filesystem command blocked. Use an explicit, reviewed, "
            "narrow operation after confirming the target and authorization."
        )
        return
    if BARE_ENV.search(command):
        deny(
            "Use the canonical project environment: Make targets, .venv/bin/python, "
            "or .venv/bin/uv; do not use a global Python, pip, or uv executable."
        )


if __name__ == "__main__":
    main()
