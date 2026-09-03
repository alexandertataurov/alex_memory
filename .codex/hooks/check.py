#!/usr/bin/env python3
"""Validate local Codex workflow configuration without reading private project data."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".codex" / "hooks"
CONFIG = ROOT / ".codex" / "hooks.json"
CONTROL_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "TASKS.md",
    ROOT / "docs" / "PLANS.md",
    ROOT / "docs" / "DEVELOPMENT.md",
    ROOT / ".codex" / "hooks" / "session_start.py",
)
STALE_CONTROL_PATTERNS = (
    re.compile(r"no initial commit yet", re.IGNORECASE),
    re.compile(r"repository execution authority", re.IGNORECASE),
    re.compile(r"repository .* authoritative .* task", re.IGNORECASE),
    re.compile(r"`?TASKS\.md`? is (?:the )?(?:single )?authoritative[^\n]*queue", re.IGNORECASE),
    re.compile(r"create or move one task to \*\*Now\*\*", re.IGNORECASE),
    re.compile(r"Repo ID[^\n]*(?:is|required|require)[^\n]*(?:executable|authorization|runnable)", re.IGNORECASE),
)


def run_sample(script: str, event: dict[str, object]) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        cwd=ROOT,
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{script} exited {result.returncode}: {result.stderr.strip()}"
        )
    if script != "session_start.py" and result.stdout.strip():
        json.loads(result.stdout)


def check_control_policy() -> None:
    violations: list[str] = []
    for path in CONTROL_FILES:
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(pattern.search(line) for pattern in STALE_CONTROL_PATTERNS):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: stale work-control wording")
    if violations:
        raise RuntimeError("\n".join(violations))


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    required = {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}
    if not required.issubset(config.get("hooks", {})):
        raise RuntimeError("hooks.json is missing one or more required hook events")
    for script in HOOKS.glob("*.py"):
        compile(script.read_text(encoding="utf-8"), str(script), "exec")
    run_sample("pre_tool_policy.py", {"tool_input": {"command": "make check"}})
    run_sample("post_python_check.py", {"tool_input": {"patch": ""}})
    run_sample(
        "stop_review.py", {"last_assistant_message": "No implementation changes."}
    )
    check_control_policy()
    print("Codex workflow: configuration, syntax, samples, and authority policy pass.")


if __name__ == "__main__":
    main()
