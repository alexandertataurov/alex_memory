#!/usr/bin/env python3
"""Emit compact, private-safe live session state for Alex Memory."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def main() -> None:
    branch = git_value("branch", "--show-current")
    status = git_value("status", "--short")
    changed = "clean" if not status else f"{len(status.splitlines())} changed path(s)"
    head = git_value("log", "-1", "--pretty=%h %s")

    print("Alex Memory")
    print(f"Branch: {branch}")
    print(f"Worktree: {changed}")
    print(f"HEAD: {head}")
    print("Next action: use alex-memory-loop → Codex — Ready & Authorized → lowest-sequence unblocked leaf.")
    print("Completion gates: Fast=targeted tests+Ruff | Standard=make check | Risky=make verify.")
    print("Private data boundary: never inspect or modify .env, data/, sessions, logs, media, or backups unless an explicitly authorized safe operation requires it.")


if __name__ == "__main__":
    main()
