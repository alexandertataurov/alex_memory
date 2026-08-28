"""Read-only readiness inventory for bounded derived-state repair."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from .schema_support import fts5_available


REPAIR_OPERATIONS = frozenset({"fts", "task-project", "segments", "context"})


def derived_state_repair_inventory(
    conn: sqlite3.Connection, *, limit: int = 500
) -> dict[str, int | bool]:
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


def _operation_report(
    name: str, inventory: dict[str, int | bool]
) -> dict[str, int | bool]:
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
        "eligible_units": int(inventory[f"{prefix}_candidates"]),
        "truncated": bool(inventory[f"{prefix}_truncated"]),
    }


def _bounded_count(conn: sqlite3.Connection, query: str, limit: int) -> int:
    return sum(1 for _ in conn.execute(query, (limit,)))
