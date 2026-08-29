"""Revision-safe, bounded refresh of materialized context after projection."""

from __future__ import annotations

import sqlite3
from typing import cast

from ..config import Settings
from ..utils import utc_now


def enqueue_context_invalidations(
    conn: sqlite3.Connection, batch_id: int, scopes: set[tuple[str, int]]
) -> dict[tuple[str, int], int]:
    """Coalesce affected scopes and retain the revision owned by this batch."""
    revisions = _enqueue_context_scopes(conn, scopes)
    for scope_type, scope_id in sorted(scopes):
        conn.execute(
            """INSERT INTO ai_batch_invalidations(batch_id,scope_type,scope_id,requested_revision)
               VALUES (?,?,?,?) ON CONFLICT(batch_id,scope_type,scope_id)
               DO UPDATE SET requested_revision=excluded.requested_revision,integrated_at=NULL""",
            (batch_id, scope_type, scope_id, revisions[(scope_type, scope_id)]),
        )
    return revisions


def enqueue_context_refresh(
    conn: sqlite3.Connection, scopes: set[tuple[str, int]]
) -> None:
    """Request explicit derived refresh without inventing a source batch."""
    _enqueue_context_scopes(conn, scopes)


def _enqueue_context_scopes(
    conn: sqlite3.Connection, scopes: set[tuple[str, int]]
) -> dict[tuple[str, int], int]:
    """Coalesce scope revisions and return their durable revision numbers."""
    now = utc_now()
    revisions: dict[tuple[str, int], int] = {}
    for scope_type, scope_id in sorted(scopes):
        row = conn.execute(
            "SELECT requested_revision FROM context_invalidations WHERE scope_type=? AND scope_id=?",
            (scope_type, scope_id),
        ).fetchone()
        revision = int(row[0]) + 1 if row else 1
        conn.execute(
            """INSERT INTO context_invalidations(
                   scope_type,scope_id,requested_revision,completed_revision,status,updated_at
               ) VALUES (?,?,?,0,'pending',?)
               ON CONFLICT(scope_type,scope_id) DO UPDATE SET
                 requested_revision=excluded.requested_revision,status='pending',
                 last_error=NULL,updated_at=excluded.updated_at""",
            (scope_type, scope_id, revision, now),
        )
        revisions[(scope_type, scope_id)] = revision
    return revisions


async def refresh_pending_context(
    conn: sqlite3.Connection, settings: Settings, limit: int = 20
) -> int:
    """Refresh at most ``limit`` invalidated scopes; failures stay retryable."""
    if limit < 1:
        raise ValueError("context refresh limit must be positive")
    rows = cast(
        list[tuple[str, int, int]],
        conn.execute(
            """SELECT scope_type,scope_id,requested_revision FROM context_invalidations
           WHERE status IN ('pending','failed')
           ORDER BY updated_at,scope_type,scope_id LIMIT ?""",
            (limit,),
        ).fetchall(),
    )
    return await _refresh_rows(conn, settings, rows)


async def refresh_selected_conversations(
    conn: sqlite3.Connection,
    settings: Settings,
    revisions: tuple[tuple[int, int], ...],
) -> int:
    """Refresh exact pending conversation revisions without invoking profile work."""
    if not revisions:
        raise ValueError("conversation refresh revisions must be non-empty")
    if len(revisions) > 500:
        raise ValueError("conversation refresh revisions must be bounded")
    rows: list[tuple[str, int, int]] = []
    for conversation_id, revision in revisions:
        row = conn.execute(
            """SELECT scope_type,scope_id,requested_revision FROM context_invalidations
               WHERE scope_type='conversation' AND scope_id=? AND requested_revision=?
                 AND status IN ('pending','failed')""",
            (conversation_id, revision),
        ).fetchone()
        if row is not None:
            rows.append(cast(tuple[str, int, int], row))
    return await _refresh_rows(conn, settings, rows)


async def _refresh_rows(
    conn: sqlite3.Connection,
    settings: Settings,
    rows: list[tuple[str, int, int]],
) -> int:
    """Claim and refresh already-selected durable invalidation rows."""
    completed = 0
    for scope_type, scope_id, revision in rows:
        with conn:
            claimed = conn.execute(
                """UPDATE context_invalidations SET status='running',attempt_count=attempt_count+1,
                   last_error=NULL,updated_at=?
                   WHERE scope_type=? AND scope_id=? AND requested_revision=?
                     AND status IN ('pending','failed')""",
                (utc_now(), scope_type, scope_id, revision),
            )
        if not claimed.rowcount:
            continue
        try:
            await _refresh_scope(conn, settings, str(scope_type), int(scope_id))
        except Exception as error:
            with conn:
                conn.execute(
                    """UPDATE context_invalidations SET status='failed',last_error=?,updated_at=?
                       WHERE scope_type=? AND scope_id=?""",
                    (
                        f"{type(error).__name__}: {error}"[:2000],
                        utc_now(),
                        scope_type,
                        scope_id,
                    ),
                )
            continue
        with conn:
            now = utc_now()
            conn.execute(
                """UPDATE context_invalidations SET completed_revision=MAX(completed_revision,?),
                   status=CASE WHEN requested_revision>? THEN 'pending' ELSE 'clean' END,
                   updated_at=? WHERE scope_type=? AND scope_id=?""",
                (revision, revision, now, scope_type, scope_id),
            )
            conn.execute(
                """UPDATE ai_batch_invalidations SET integrated_at=?
                   WHERE scope_type=? AND scope_id=? AND requested_revision<=? AND integrated_at IS NULL""",
                (now, scope_type, scope_id, revision),
            )
            conn.execute(
                """UPDATE ai_batches SET context_integrated_at=?
                   WHERE batch_id IN (
                       SELECT b.batch_id FROM ai_batch_invalidations AS b
                       GROUP BY b.batch_id HAVING SUM(CASE WHEN b.integrated_at IS NULL THEN 1 ELSE 0 END)=0
                   ) AND context_integrated_at IS NULL""",
                (now,),
            )
        completed += 1
    return completed


async def _refresh_scope(
    conn: sqlite3.Connection, settings: Settings, scope_type: str, scope_id: int
) -> None:
    if scope_type == "conversation":
        from ..operational import _refresh_summaries
        from .segments import ConversationSegmenter

        date_value = conn.execute(
            "SELECT MIN(date) FROM messages WHERE chat_id=?", (scope_id,)
        ).fetchone()[0]
        _refresh_summaries(conn, scope_id, date_value)
        ConversationSegmenter(conn).rebuild_chat(scope_id)
        return
    if scope_type == "person":
        from .contact_materializer import ContactContextMaterializer
        from ..profile_summary import refresh_profile_summary

        ContactContextMaterializer(conn).refresh_person(scope_id)
        await refresh_profile_summary(conn, settings, scope_id)
        return
    if scope_type == "global":
        from ..intelligence import refresh_operational_state
        from .service import ContextService

        ContextService(conn, settings).snapshot_global_state()
        refresh_operational_state(conn, settings)
        return
    # Project/company/task materialization has no separate table owner yet.
    # Their invalidation is still durable and satisfied by the global refresh.
