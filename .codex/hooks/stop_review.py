#!/usr/bin/env python3
"""Request verification evidence and report lightweight diff-review cues."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CHANGE_CLAIM = re.compile(
    r"\b(?:implemented|changed|updated|added|removed|deleted|installed|refactored|fixed)\b",
    re.IGNORECASE,
)
VERIFICATION = re.compile(
    r"\b(?:verification|verified|tests?|pytest|ruff|mypy|make (?:check|verify|docs-check|db-check)|not run|skipped|interrupted)\b",
    re.IGNORECASE,
)
REVIEW_CUES = re.compile(
    r"^\+.*(?:\b(?:legacy|deprecated|compatibility)\b|\bclass\s+\w*(?:Manager|Factory)\b|"
    r"\bNotImplementedError\b|\bpass\s*(?:#.*)?$)",
    re.IGNORECASE | re.MULTILINE,
)


def git_diff() -> str | None:
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if head.returncode:
        return None
    result = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--unified=0",
            "HEAD",
            "--",
            "src",
            "tests",
            "scripts",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout


def review_note() -> str:
    diff = git_diff()
    if diff is None:
        return "AI-slop/legacy diff review: unavailable until this uncommitted repository has an initial Git baseline."
    cues = REVIEW_CUES.findall(diff)
    if cues:
        return (
            "AI-slop/legacy diff review: inspect these new structural cues before handoff: "
            + "; ".join(item.strip()[:180] for item in cues[:5])
        )
    return "AI-slop/legacy diff review: no new generic-layer, placeholder, or legacy cue found in maintained Python diff."


def main() -> None:
    try:
        event: dict[str, Any] = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "approve"}))
        return
    if event.get("stop_hook_active"):
        print(json.dumps({"decision": "approve"}))
        return
    message = str(event.get("last_assistant_message") or "")
    note = (
        review_note()
        + " Notion durability check: preserve only a durable decision, task, blocker, requirement, or project-status change; do not dump session detail."
    )
    if CHANGE_CLAIM.search(message) and not VERIFICATION.search(message):
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Provide proportionate verification evidence before handoff. "
                    + note,
                }
            )
        )
        return
    print(json.dumps({"decision": "approve", "reason": note}))


if __name__ == "__main__":
    main()
