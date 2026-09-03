#!/usr/bin/env python3
"""Run lightweight checks after maintained Python files are changed by apply_patch."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MAINTAINED = (ROOT / "src", ROOT / "tests", ROOT / "scripts")
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+)$", re.MULTILINE)


def response(message: str | None = None) -> None:
    payload: dict[str, Any] = {"continue": True}
    if message:
        payload["hookSpecificOutput"] = {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    print(json.dumps(payload))


def changed_paths(event: dict[str, Any]) -> list[Path]:
    tool_input = event.get("tool_input", {})
    patch = tool_input.get("patch", "") if isinstance(tool_input, dict) else ""
    paths: list[Path] = []
    for name in PATCH_FILE.findall(str(patch)):
        candidate = (ROOT / name).resolve()
        if (
            candidate.suffix == ".py"
            and candidate.exists()
            and any(candidate.is_relative_to(parent) for parent in MAINTAINED)
        ):
            paths.append(candidate)
    return sorted(set(paths))


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output[-1600:]


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        response()
        return
    paths = changed_paths(event)
    if not paths:
        response()
        return

    ruff = ROOT / ".venv" / "bin" / "ruff"
    python = ROOT / ".venv" / "bin" / "python"
    if not ruff.exists() or not python.exists():
        response(
            "Fast Python checks skipped: run make setup to restore the canonical environment."
        )
        return

    relative = [str(path.relative_to(ROOT)) for path in paths]
    failures = []
    checks = [
        ("Ruff", [str(ruff), "check", *relative]),
        ("Compile", [str(python), "-m", "py_compile", *relative]),
    ]
    for label, command in checks:
        code, output = run(command)
        if code:
            failures.append(
                f"{label} failed for {', '.join(relative)}:\n{output or '(no output)'}"
            )
    response("\n\n".join(failures) if failures else None)


if __name__ == "__main__":
    main()
