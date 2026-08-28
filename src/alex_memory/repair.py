"""Read-only readiness inventory for bounded derived-state repair."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import cast

from .config import Settings
from .database import set_app_meta
from .operational import backfill_task_project_links
from .schema_support import fts5_available


REPAIR_OPERATIONS = frozenset({"fts", "task-project", "segments", "context"})


def derived_state_repair_inventory(
    conn: sqlite3.Connection, *, limit: int = 500
) -> dict[str, object]:
    """Count the first repair units without exposing content or writing rows.

    Counts are deliberately capped so a future operator command cannot turn an
    inventory into an unbounded scan. A true `*_truncated` value means the
    reported count is the supplied limit, not the full eligible population.
    """
    if limit < 1:
        raise ValueError("repair inventory limit must be positive")
    probe_limit = limit + 1
    task_links = _bounded_count(
        conn,
        """SELECT 1 FROM tasks AS t JOIN ai_items AS i ON i.item_id=t.source_item_id
           WHERE t.related_project_id IS NULL AND t.source_chat_id IS NOT NULL
           ORDER BY t.task_id LIMIT ?""",
        probe_limit,
    )
    task_project_unit_fingerprint = _task_project_unit_fingerprint(conn, limit)
    segment_chats = _bounded_count(
        conn,
        """SELECT DISTINCT source_chat_id FROM tasks
           WHERE related_project_id IS NOT NULL AND source_chat_id IS NOT NULL
           ORDER BY source_chat_id LIMIT ?""",
        probe_limit,
    )
    pending_context = _bounded_count(
        conn,
        """SELECT 1 FROM context_invalidations
           WHERE status IN ('pending','failed')
           ORDER BY updated_at,scope_type,scope_id LIMIT ?""",
        probe_limit,
    )
    return {
        "fts_rebuild_available": fts5_available(conn),
        "task_project_candidates": min(task_links, limit),
        "task_project_truncated": task_links > limit,
        "task_project_unit_fingerprint": task_project_unit_fingerprint,
        "segment_chat_candidates": min(segment_chats, limit),
        "segment_chat_truncated": segment_chats > limit,
        "pending_context_candidates": min(pending_context, limit),
        "pending_context_truncated": pending_context > limit,
    }


def derived_state_repair_dry_run(
    conn: sqlite3.Connection, *, operations: set[str], limit: int = 500
) -> dict[str, object]:
    """Report one explicit finite repair scope without changing SQLite state."""
    selected = sorted(operations)
    if not selected:
        raise ValueError("repair dry-run requires at least one operation")
    unsupported = set(selected) - REPAIR_OPERATIONS
    if unsupported:
        raise ValueError(
            f"unsupported repair operations: {', '.join(sorted(unsupported))}"
        )
    inventory = derived_state_repair_inventory(conn, limit=limit)
    report: dict[str, object] = {
        "mode": "dry-run",
        "limit": limit,
        "operations": {name: _operation_report(name, inventory) for name in selected},
    }
    report["fingerprint"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def apply_task_project_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
    limit: int = 500,
) -> dict[str, object]:
    """Apply one fingerprinted task-project repair unit transactionally.

    The stored checkpoint is deliberately keyed by the dry-run fingerprint.
    Retrying a completed unit returns its recorded outcome; an interrupted unit
    reruns the same bounded, idempotent operation in one SQLite transaction.
    """
    if not recovery_receipt.is_file():
        raise ValueError("repair apply requires an existing recovery receipt")
    if recovery_receipt.resolve() == settings.db_path.resolve():
        raise ValueError("repair recovery receipt must not be the target database")
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(
        conn, operations={"task-project"}, limit=limit
    )
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    task_ids = _task_project_candidate_ids(conn, limit)
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "task-project",
        "limit": limit,
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "task_ids": task_ids,
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        with conn:
            linked, reviewed = backfill_task_project_links(
                conn,
                settings,
                limit=limit,
                task_ids=tuple(task_ids),
            )
            outcome = {
                "fingerprint": dry_run_fingerprint,
                "linked": linked,
                "reviewed": reviewed,
            }
            set_app_meta(
                conn,
                key,
                json.dumps(
                    {**checkpoint, "status": "completed", "outcome": outcome},
                    sort_keys=True,
                ),
            )
    except Exception as error:
        with conn:
            set_app_meta(
                conn,
                key,
                json.dumps(
                    {
                        **checkpoint,
                        "status": "failed",
                        "error": f"{type(error).__name__}: {error}"[:500],
                    },
                    sort_keys=True,
                ),
            )
        raise
    return {"status": "completed", **outcome}


def _operation_report(name: str, inventory: dict[str, object]) -> dict[str, object]:
    if name == "fts":
        return {
            "eligible_units": int(bool(inventory["fts_rebuild_available"])),
            "truncated": False,
        }
    prefix = {
        "task-project": "task_project",
        "segments": "segment_chat",
        "context": "pending_context",
    }[name]
    return {
        "eligible_units": cast(int, inventory[f"{prefix}_candidates"]),
        "truncated": bool(inventory[f"{prefix}_truncated"]),
        **(
            {"unit_fingerprint": str(inventory["task_project_unit_fingerprint"])}
            if name == "task-project"
            else {}
        ),
    }


def _bounded_count(conn: sqlite3.Connection, query: str, limit: int) -> int:
    return sum(1 for _ in conn.execute(query, (limit,)))


def _task_project_candidate_ids(conn: sqlite3.Connection, limit: int) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute(
            """SELECT t.task_id FROM tasks AS t
               JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.related_project_id IS NULL AND t.source_chat_id IS NOT NULL
               ORDER BY t.task_id LIMIT ?""",
            (limit,),
        )
    ]


def _task_project_unit_fingerprint(conn: sqlite3.Connection, limit: int) -> str:
    return hashlib.sha256(
        json.dumps(
            _task_project_candidate_ids(conn, limit), separators=(",", ":")
        ).encode()
    ).hexdigest()
