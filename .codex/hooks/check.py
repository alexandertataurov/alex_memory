#!/usr/bin/env python3
"""Validate local Codex hook configuration without reading private project data."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".codex" / "hooks"
CONFIG = ROOT / ".codex" / "hooks.json"


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
    print("Codex hooks: configuration, syntax, and private-safe samples pass.")


if __name__ == "__main__":
    main()
