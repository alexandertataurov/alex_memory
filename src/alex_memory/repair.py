"""Read-only readiness inventory for bounded derived-state repair."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import cast

from .config import Settings
from .database import set_app_meta
from .context.segments import ConversationSegmenter
from .context.refresh import refresh_selected_conversations
from .operational import TASK_KINDS, TaskReconciler, backfill_task_project_links
from .intelligence import evaluate_project_health
from .schema_support import fts5_available, fts_source_fingerprint, rebuild_fts


REPAIR_OPERATIONS = frozenset(
    {"fts", "task-project", "task-lifecycle", "segments", "context", "project-health"}
)


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
    task_lifecycle_items = _task_lifecycle_candidate_rows(conn, limit)
    task_lifecycle_unit_fingerprint = _task_lifecycle_unit_fingerprint(
        task_lifecycle_items
    )
    segment_chats = _bounded_count(
        conn,
        """SELECT DISTINCT source_chat_id FROM tasks
           WHERE related_project_id IS NOT NULL AND source_chat_id IS NOT NULL
           ORDER BY source_chat_id LIMIT ?""",
        probe_limit,
    )
    segment_chat_unit_fingerprint = _segment_chat_unit_fingerprint(conn, limit)
    pending_context = _bounded_count(
        conn,
        """SELECT 1 FROM context_invalidations
           WHERE scope_type='conversation' AND status IN ('pending','failed')
           ORDER BY updated_at,scope_type,scope_id LIMIT ?""",
        probe_limit,
    )
    context_unit_fingerprint = _context_unit_fingerprint(conn, limit)
    project_health = _bounded_count(
        conn,
        """SELECT 1 FROM projects WHERE status NOT IN ('completed','archived')
           ORDER BY project_id LIMIT ?""",
        probe_limit,
    )
    project_health_unit_fingerprint = _project_health_unit_fingerprint(conn, limit)
    return {
        "fts_rebuild_available": fts5_available(conn),
        "fts_unit_fingerprint": fts_source_fingerprint(conn),
        "task_project_candidates": min(task_links, limit),
        "task_project_truncated": task_links > limit,
        "task_project_unit_fingerprint": task_project_unit_fingerprint,
        "task_lifecycle_candidates": len(task_lifecycle_items),
        "task_lifecycle_truncated": _task_lifecycle_candidate_count(conn, limit)
        > limit,
        "task_lifecycle_unit_fingerprint": task_lifecycle_unit_fingerprint,
        "segment_chat_candidates": min(segment_chats, limit),
        "segment_chat_truncated": segment_chats > limit,
        "segment_chat_unit_fingerprint": segment_chat_unit_fingerprint,
        "pending_context_candidates": min(pending_context, limit),
        "pending_context_truncated": pending_context > limit,
        "pending_context_unit_fingerprint": context_unit_fingerprint,
        "project_health_candidates": min(project_health, limit),
        "project_health_truncated": project_health > limit,
        "project_health_unit_fingerprint": project_health_unit_fingerprint,
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
    _validate_recovery_receipt(settings, recovery_receipt)
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


def apply_task_lifecycle_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
    limit: int = 500,
) -> dict[str, object]:
    """Replay one exact, claim-backed task-item set through ``TaskReconciler``.

    This fixture-only unit never reconstructs work from canonical task rows.
    Every selected item has immutable claim evidence for its exact source
    message, and the checkpoint retains its source/item membership privately.
    """
    _validate_recovery_receipt(settings, recovery_receipt)
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(
        conn, operations={"task-lifecycle"}, limit=limit
    )
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    rows = _task_lifecycle_candidate_rows(conn, limit)
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "task-lifecycle",
        "limit": limit,
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "source_items": [
            {
                "item_id": int(cast(int, row[0])),
                "source_claim_id": int(cast(int, row[11])),
                "source_chat_id": int(cast(int, row[8])),
                "source_message_id": int(cast(int, row[10])),
                "person_id": row[12],
                "company_id": row[13],
                "project_id": row[14],
            }
            for row in rows
        ],
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        with conn:
            outcome = _reconcile_task_lifecycle_rows(conn, settings, rows)
            outcome["fingerprint"] = dry_run_fingerprint
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


def apply_segment_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
    limit: int = 500,
) -> dict[str, object]:
    """Rebuild one exact bounded set of task-anchored segment chats.

    This fixture-only operation replaces only `task_anchors` segment rows from
    their linked canonical task inputs. Its fingerprint and checkpoint prevent a
    resume from silently changing the selected chats.
    """
    _validate_recovery_receipt(settings, recovery_receipt)
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(conn, operations={"segments"}, limit=limit)
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    chat_ids = _segment_chat_candidate_ids(conn, limit)
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "segments",
        "limit": limit,
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "chat_ids": chat_ids,
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        with conn:
            segments = ConversationSegmenter(conn).rebuild_chats(set(chat_ids))
            outcome = {
                "fingerprint": dry_run_fingerprint,
                "chats": len(chat_ids),
                "segments": segments,
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


def apply_fts_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
) -> dict[str, object]:
    """Rebuild all FTS-derived rows atomically from one verified source state."""
    _validate_recovery_receipt(settings, recovery_receipt)
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(conn, operations={"fts"})
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    operations = cast(dict[str, dict[str, object]], report["operations"])
    unit_fingerprint = operations["fts"]["unit_fingerprint"]
    if unit_fingerprint is None:
        raise ValueError("FTS repair is unavailable on this SQLite build")
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "fts",
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "source_fingerprint": unit_fingerprint,
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        rebuild_fts(conn)
        outcome = {
            "fingerprint": dry_run_fingerprint,
            "source_fingerprint": unit_fingerprint,
        }
        set_app_meta(
            conn,
            key,
            json.dumps(
                {**checkpoint, "status": "completed", "outcome": outcome},
                sort_keys=True,
            ),
        )
        conn.commit()
    except Exception as error:
        conn.rollback()
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


def apply_context_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
    limit: int = 500,
) -> dict[str, object]:
    """Refresh only the exact selected deterministic conversation contexts."""
    _validate_recovery_receipt(settings, recovery_receipt)
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(conn, operations={"context"}, limit=limit)
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    revisions = _context_candidate_revisions(conn, limit)
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "context",
        "limit": limit,
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "conversation_revisions": revisions,
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        completed = asyncio.run(
            refresh_selected_conversations(conn, settings, tuple(revisions))
        )
        unfinished = [
            (conversation_id, revision)
            for conversation_id, revision in revisions
            if not _context_revision_completed(conn, conversation_id, revision)
        ]
        if unfinished:
            raise RuntimeError("selected conversation context refresh did not complete")
        outcome = {
            "fingerprint": dry_run_fingerprint,
            "conversations": completed,
        }
        with conn:
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


def apply_project_health_repair(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    dry_run_fingerprint: str,
    recovery_receipt: Path,
    limit: int = 500,
) -> dict[str, object]:
    """Recompute one exact bounded project-health set without notifications."""
    _validate_recovery_receipt(settings, recovery_receipt)
    key = f"derived_state_repair:{dry_run_fingerprint}"
    prior = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    if prior is not None:
        stored = json.loads(str(prior[0]))
        if stored.get("status") == "completed":
            return {"status": "already-complete", **stored["outcome"]}
    report = derived_state_repair_dry_run(
        conn, operations={"project-health"}, limit=limit
    )
    if report["fingerprint"] != dry_run_fingerprint:
        raise ValueError("repair apply dry-run fingerprint no longer matches")
    project_ids = _project_health_candidate_ids(conn, limit)
    checkpoint: dict[str, object] = {
        "status": "running",
        "operation": "project-health",
        "limit": limit,
        "recovery_receipt": str(recovery_receipt),
        "fingerprint": dry_run_fingerprint,
        "project_ids": project_ids,
        "evaluation_date": date.today().isoformat(),
    }
    with conn:
        set_app_meta(conn, key, json.dumps(checkpoint, sort_keys=True))
    try:
        with conn:
            changed = evaluate_project_health(
                conn,
                settings,
                date.fromisoformat(str(checkpoint["evaluation_date"])),
                project_ids=tuple(project_ids),
                emit_notifications=False,
            )
            outcome = {
                "fingerprint": dry_run_fingerprint,
                "projects": len(project_ids),
                "changed": changed,
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
            "unit_fingerprint": inventory["fts_unit_fingerprint"],
        }
    prefix = {
        "task-project": "task_project",
        "task-lifecycle": "task_lifecycle",
        "segments": "segment_chat",
        "context": "pending_context",
        "project-health": "project_health",
    }[name]
    report: dict[str, object] = {
        "eligible_units": cast(int, inventory[f"{prefix}_candidates"]),
        "truncated": bool(inventory[f"{prefix}_truncated"]),
    }
    if name == "task-project":
        report["unit_fingerprint"] = str(inventory["task_project_unit_fingerprint"])
    elif name == "task-lifecycle":
        report["unit_fingerprint"] = str(inventory["task_lifecycle_unit_fingerprint"])
    elif name == "segments":
        report["unit_fingerprint"] = str(inventory["segment_chat_unit_fingerprint"])
    elif name == "context":
        report["unit_fingerprint"] = str(inventory["pending_context_unit_fingerprint"])
    elif name == "project-health":
        report["unit_fingerprint"] = str(inventory["project_health_unit_fingerprint"])
    return report


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


def _task_lifecycle_candidate_count(conn: sqlite3.Connection, limit: int) -> int:
    return sum(1 for _ in _task_lifecycle_candidate_rows(conn, limit + 1))


def _task_lifecycle_candidate_rows(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[object, ...]]:
    """Select only unfinished, exact-evidence task decisions in a bounded order."""
    placeholders = ",".join("?" for _ in TASK_KINDS)
    return [
        tuple(row)
        for row in conn.execute(
            f"""SELECT i.item_id,i.kind,i.title,i.details,i.status,i.owner,i.due_date,
                       i.confidence,i.source_chat_id,i.source_date,i.source_message_id,
                       i.source_claim_id,i.person_id,i.company_id,i.project_id
                  FROM ai_items AS i
                  JOIN semantic_claims AS claim ON claim.claim_id=i.source_claim_id
                  JOIN messages AS message
                    ON message.chat_id=i.source_chat_id
                   AND message.message_id=i.source_message_id
                 WHERE i.kind IN ({placeholders})
                   AND i.source_chat_id IS NOT NULL
                   AND i.source_message_id IS NOT NULL
                   AND i.source_claim_id IS NOT NULL
                   AND COALESCE(message.is_deleted,0)=0
                   AND claim.authority_status IN ('observed','accepted','manual')
                   AND EXISTS (
                       SELECT 1 FROM semantic_claim_evidence AS evidence
                       WHERE evidence.claim_id=i.source_claim_id
                         AND evidence.source_chat_id=i.source_chat_id
                         AND evidence.source_message_id=i.source_message_id
                   )
                   AND NOT EXISTS (
                       SELECT 1 FROM task_events AS event
                       WHERE event.source='ai' AND event.source_item_id=i.item_id
                   )
                   AND NOT EXISTS (
                       SELECT 1 FROM review_queue AS review
                       WHERE review.subject_type='ai_item' AND review.subject_id=i.item_id
                   )
                 ORDER BY i.item_id LIMIT ?""",
            (*sorted(TASK_KINDS), limit),
        )
    ]


def _task_lifecycle_unit_fingerprint(rows: list[tuple[object, ...]]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _reconcile_task_lifecycle_rows(
    conn: sqlite3.Connection, settings: Settings, rows: list[tuple[object, ...]]
) -> dict[str, object]:
    """Run only checkpoint-selected source items through the canonical reducer."""
    before_tasks = int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
    before_reviews = int(
        conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
    )
    reconciler = TaskReconciler(conn, settings)
    reconciled = 0
    for row in rows:
        task_id = reconciler.process_item(
            row[:9],
            cast(int | None, row[12]),
            cast(int | None, row[13]),
            cast(int | None, row[14]),
            source_claim_id=int(cast(int, row[11])),
            source_at=cast(str | None, row[9]),
        )
        reconciled += int(task_id is not None)
    return {
        "source_items": len(rows),
        "reconciled": reconciled,
        "tasks_created": int(conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        - before_tasks,
        "reviews_created": int(
            conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
        )
        - before_reviews,
    }


def _segment_chat_candidate_ids(conn: sqlite3.Connection, limit: int) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute(
            """SELECT DISTINCT source_chat_id FROM tasks
               WHERE related_project_id IS NOT NULL AND source_chat_id IS NOT NULL
               ORDER BY source_chat_id LIMIT ?""",
            (limit,),
        )
    ]


def _segment_chat_unit_fingerprint(conn: sqlite3.Connection, limit: int) -> str:
    return hashlib.sha256(
        json.dumps(
            _segment_chat_candidate_ids(conn, limit), separators=(",", ":")
        ).encode()
    ).hexdigest()


def _context_candidate_revisions(
    conn: sqlite3.Connection, limit: int
) -> list[tuple[int, int]]:
    return [
        (int(row[0]), int(row[1]))
        for row in conn.execute(
            """SELECT scope_id,requested_revision FROM context_invalidations
               WHERE scope_type='conversation' AND status IN ('pending','failed')
               ORDER BY updated_at,scope_id LIMIT ?""",
            (limit,),
        )
    ]


def _context_unit_fingerprint(conn: sqlite3.Connection, limit: int) -> str:
    return hashlib.sha256(
        json.dumps(
            _context_candidate_revisions(conn, limit), separators=(",", ":")
        ).encode()
    ).hexdigest()


def _context_revision_completed(
    conn: sqlite3.Connection, conversation_id: int, revision: int
) -> bool:
    row = conn.execute(
        """SELECT completed_revision FROM context_invalidations
           WHERE scope_type='conversation' AND scope_id=?""",
        (conversation_id,),
    ).fetchone()
    return row is not None and int(row[0]) >= revision


def _project_health_candidate_ids(conn: sqlite3.Connection, limit: int) -> list[int]:
    return [
        int(row[0])
        for row in conn.execute(
            """SELECT project_id FROM projects WHERE status NOT IN ('completed','archived')
               ORDER BY project_id LIMIT ?""",
            (limit,),
        )
    ]


def _project_health_unit_fingerprint(conn: sqlite3.Connection, limit: int) -> str:
    project_ids = _project_health_candidate_ids(conn, limit)
    digest = hashlib.sha256()
    digest.update(date.today().isoformat().encode())
    if not project_ids:
        return digest.hexdigest()
    placeholders = ",".join("?" for _ in project_ids)
    for query, params in (
        (
            f"""SELECT project_id,status,health_score,last_activity_at,updated_at FROM projects
                WHERE project_id IN ({placeholders}) ORDER BY project_id""",
            tuple(project_ids),
        ),
        (
            f"""SELECT task_id,related_project_id,status,due_date,created_at,updated_at,source_item_id
                FROM tasks WHERE related_project_id IN ({placeholders})
                ORDER BY related_project_id,task_id""",
            tuple(project_ids),
        ),
        (
            f"""SELECT item_id,project_id,source_date,created_at FROM ai_items
                WHERE project_id IN ({placeholders}) OR item_id IN (
                    SELECT source_item_id FROM tasks
                    WHERE related_project_id IN ({placeholders})
                ) ORDER BY item_id""",
            tuple(project_ids) * 2,
        ),
        (
            f"""SELECT event_id,project_id,occurred_at,observed_at FROM context_events
                WHERE project_id IN ({placeholders}) ORDER BY project_id,event_id""",
            tuple(project_ids),
        ),
        (
            f"""SELECT segment_id,project_id,started_at,ended_at,updated_at
                FROM conversation_segments WHERE project_id IN ({placeholders})
                ORDER BY project_id,segment_id""",
            tuple(project_ids),
        ),
    ):
        digest.update(query.encode())
        for row in conn.execute(query, params):
            digest.update(json.dumps(tuple(row), separators=(",", ":")).encode())
    return digest.hexdigest()


def _validate_recovery_receipt(settings: Settings, recovery_receipt: Path) -> None:
    if not recovery_receipt.is_file():
        raise ValueError("repair apply requires an existing recovery receipt")
    if recovery_receipt.resolve() == settings.db_path.resolve():
        raise ValueError("repair recovery receipt must not be the target database")
