#!/usr/bin/env python3
"""Emit compact, private-safe session guidance for Alex Memory."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def active_task() -> str:
    tasks = ROOT / "TASKS.md"
    if not tasks.exists():
        return "unavailable"
    now = False
    for line in tasks.read_text(encoding="utf-8").splitlines():
        if line == "## Now":
            now = True
            continue
        if now and line.startswith("## "):
            break
        if now and line.startswith("- [ ] AM-"):
            return line.split(" —", 1)[0].removeprefix("- [ ] ")
    return "none"


def main() -> None:
    branch = git_value("branch", "--show-current")
    status = git_value("status", "--short")
    changed = "clean" if not status else f"{len(status.splitlines())} changed path(s)"
    print(
        "Notion is available as persistent project memory; retrieve it lazily for historical, business, or decision work."
    )
    print(
        "Alex Memory | "
        f"branch: {branch} | worktree: {changed} | active task: {active_task()}\n"
        "Canonical environment: .venv/bin/python and .venv/bin/uv; use make targets. "
        "Private data stays private: never inspect or modify .env, data/, Telegram sessions, logs, media, or backups.\n"
        "Follow evidence -> observations -> canonical state -> bounded context. "
        "Hooks are workflow guardrails, not a correctness or security boundary."
    )


if __name__ == "__main__":
    main()
