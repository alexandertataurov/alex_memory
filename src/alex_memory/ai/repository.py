from __future__ import annotations

import hashlib
import json
import re
import math
import sqlite3
from dataclasses import replace
from datetime import date

from ..config import Settings
from ..classification import CLASSIFICATION_VERSION, classify_pending_messages
from ..models import AIAnalysisResult, AIBatch, AIMessage, AISaveResult
from ..utils import utc_now
from .batching import build_ai_batches
from .claims import legacy_item_claim, save_claim
from .context import add_contextual_preamble, add_history_context
from .extraction_contract import (
    ANALYSIS_VERSION,
    validate_item_shape,
    validate_response,
)


def _context_graph_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key='context_graph_version'"
    ).fetchone()
    try:
        return int(row[0]) if row else 1
    except (TypeError, ValueError):
        return 1


def _classification_chat_sql(alias: str = "c") -> str:
    not_bot = f"COALESCE({alias}.is_bot, 0) = 0"
    policy = (
        f"COALESCE((SELECT mode FROM chat_ai_policy AS p "
        f"WHERE p.chat_id = {alias}.chat_id), 'auto') <> 'exclude'"
    )
    return f"{not_bot} AND {policy}"


def _eligible_chat_sql(settings: Settings, alias: str = "c") -> str:
    """Return chats allowed to receive semantic AI work in either lane."""
    policy_mode = (
        f"COALESCE((SELECT mode FROM chat_ai_policy AS p "
        f"WHERE p.chat_id = {alias}.chat_id), 'auto')"
    )
    policy = f"{policy_mode} NOT IN ('exclude', 'classify_only')"
    included_by_policy = f"{policy_mode} = 'include'"
    if settings.ai_include_groups:
        return (
            f"{_classification_chat_sql(alias)} AND {policy} AND "
            f"(COALESCE({alias}.chat_type, 'unknown') IN ('user', 'group') "
            f"OR {included_by_policy})"
        )
    return (
        f"{_classification_chat_sql(alias)} AND {policy} AND "
        f"(COALESCE({alias}.chat_type, 'unknown') = 'user' "
        f"OR {included_by_policy})"
    )


def profile_scan_chat_sql(alias: str = "c") -> str:
    """Return explicit-policy eligibility for a user-requested profile scan."""
    policy_mode = (
        f"COALESCE((SELECT mode FROM chat_ai_policy AS p "
        f"WHERE p.chat_id = {alias}.chat_id), 'auto')"
    )
    return (
        f"{_classification_chat_sql(alias)} AND "
        f"{policy_mode} NOT IN ('exclude', 'classify_only')"
    )


def _semantic_policy_sql(alias: str = "c", classification_alias: str = "mc") -> str:
    """Apply the per-chat semantic mode after deterministic classification."""
    policy_mode = (
        f"COALESCE((SELECT mode FROM chat_ai_policy AS p "
        f"WHERE p.chat_id = {alias}.chat_id), 'auto')"
    )
    return (
        f"({policy_mode} <> 'news_only' OR "
        f"{classification_alias}.information_scope = 'external_news')"
    )


def _visible_item_sql(alias: str = "i") -> str:
    """Hide historic one-time-code facts without deleting source records."""
    title = f"LOWER({alias}.title)"
    return (
        f"({alias}.kind <> 'important_fact' OR ("
        f"{title} NOT LIKE '%login code%' AND "
        f"{title} NOT LIKE '%verification code%' AND "
        f"{title} NOT LIKE '%security code%' AND "
        f"{title} NOT LIKE '%one-time code%'"
        f"))"
    )


def get_ai_text_counts(
    conn: sqlite3.Connection,
    settings: Settings,
) -> tuple[int, int, int]:
    eligible = _eligible_chat_sql(settings)

    total_text = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id = m.chat_id AND mc.message_id = m.message_id
        WHERE TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND {eligible}
          AND {_semantic_policy_sql()}
        """
    ).fetchone()[0]

    analyzed_text = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id = m.chat_id AND mc.message_id = m.message_id
        INNER JOIN ai_message_state AS a
          ON a.chat_id = m.chat_id
         AND a.message_id = m.message_id
        WHERE TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND a.batch_id IS NOT NULL
          AND {eligible}
          AND {_semantic_policy_sql()}
        """
    ).fetchone()[0]

    pending_text = max(0, total_text - analyzed_text)
    return total_text, analyzed_text, pending_text


def get_excluded_group_text_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        """
        SELECT COUNT(*)
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        WHERE TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND COALESCE(c.chat_type, 'unknown') = 'group'
        """
    ).fetchone()[0]


def get_excluded_bot_text_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        """
        SELECT COUNT(*)
        FROM messages AS m
        INNER JOIN chats AS c ON c.chat_id = m.chat_id
        WHERE TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND c.is_bot = 1
        """
    ).fetchone()[0]


def fetch_action_items(conn: sqlite3.Connection, limit: int = 60) -> list[tuple]:
    return conn.execute(
        """
        SELECT
            i.kind,
            i.status,
            i.owner,
            i.due_date,
            i.title,
            i.details,
            i.person,
            i.company,
            i.confidence,
            COALESCE(c.title, CAST(i.source_chat_id AS TEXT))
        FROM ai_items AS i
        LEFT JOIN chats AS c ON c.chat_id = i.source_chat_id
        WHERE i.kind IN (
            'task', 'follow_up', 'deadline',
            'promise_by_me', 'promise_to_me'
        )
          AND i.status IN ('open', 'waiting')
          AND COALESCE(c.is_bot, 0) = 0
        ORDER BY
            CASE WHEN i.status = 'waiting' THEN 0 ELSE 1 END,
            CASE WHEN i.due_date IS NULL THEN 1 ELSE 0 END,
            i.due_date,
            COALESCE(i.source_date, '') DESC,
            i.item_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_ai_counts(
    conn: sqlite3.Connection,
    settings: Settings,
) -> tuple[int, int, int]:
    _, _, remaining = get_ai_text_counts(conn, settings)

    visible = _visible_item_sql()
    items = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM ai_items AS i
        LEFT JOIN chats AS c ON c.chat_id = i.source_chat_id
        WHERE COALESCE(c.is_bot, 0) = 0
          AND {visible}
        """
    ).fetchone()[0]

    open_actions = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM ai_items AS i
        LEFT JOIN chats AS c ON c.chat_id = i.source_chat_id
        WHERE i.kind IN (
            'task', 'follow_up', 'deadline',
            'promise_by_me', 'promise_to_me'
        )
          AND i.status IN ('open', 'waiting')
          AND COALESCE(c.is_bot, 0) = 0
          AND {visible}
        """
    ).fetchone()[0]

    return remaining, items, open_actions


def analyzed_message_count(
    conn: sqlite3.Connection,
    settings: Settings,
) -> int:
    _, analyzed, _ = get_ai_text_counts(conn, settings)
    return analyzed


def fetch_unanalyzed_messages(
    conn: sqlite3.Connection,
    limit: int,
    settings: Settings,
    exclude_queued_jobs: bool = False,
    after_date: str | None = None,
) -> list[AIMessage]:
    eligible = _eligible_chat_sql(settings)
    queued_filter = ""
    if exclude_queued_jobs:
        queued_filter = """
          AND NOT EXISTS (
              SELECT 1 FROM ai_job_messages AS jm
              JOIN ai_jobs AS j ON j.job_id=jm.job_id
              WHERE jm.chat_id=m.chat_id AND jm.message_id=m.message_id
                AND j.status IN ('pending','running','failed')
                AND j.analysis_version=2
          )
        """
    date_filter = ""
    parameters: list[object] = []
    if after_date:
        date_filter = "AND COALESCE(m.date, '') > ?"
        parameters.append(after_date)

    rows = conn.execute(
        f"""
        SELECT
            m.chat_id,
            m.message_id,
            m.sender_id,
            m.date,
            m.text,
            m.is_outgoing,
            COALESCE(c.title, CAST(m.chat_id AS TEXT)),
            COALESCE(c.chat_type, 'unknown')
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        LEFT JOIN ai_message_state AS a
          ON a.chat_id = m.chat_id
         AND a.message_id = m.message_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
        WHERE (a.chat_id IS NULL OR a.analysis_stale=1 OR a.analysis_version < ?)
          AND TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND COALESCE(mc.importance, 'normal') <> 'noise'
          AND COALESCE(mc.content_type, 'information') <> 'spam'
          AND {eligible}
          AND {_semantic_policy_sql()}
          {queued_filter}
          {date_filter}
        ORDER BY
            CASE COALESCE(c.chat_type, 'unknown')
                WHEN 'user' THEN 0
                WHEN 'group' THEN 1
                ELSE 2
            END,
            COALESCE(m.date, '') DESC,
            m.message_id DESC
        LIMIT ?
        """,
        (ANALYSIS_VERSION, *parameters, limit),
    ).fetchall()

    return [
        AIMessage(
            chat_id=int(row[0]),
            message_id=int(row[1]),
            sender_id=int(row[2]) if row[2] is not None else None,
            date=row[3],
            text=row[4] or "",
            is_outgoing=bool(row[5]),
            chat_title=row[6] or str(row[0]),
            chat_type=row[7] or "unknown",
        )
        for row in rows
    ]


def fetch_unclassified_messages(
    conn: sqlite3.Connection,
    limit: int,
    settings: Settings,
    classification_version: int,
) -> list[AIMessage]:
    """Return eligible evidence whose routing classification needs work."""
    eligible = _classification_chat_sql()
    rows = conn.execute(
        f"""
        SELECT m.chat_id,m.message_id,m.sender_id,m.date,m.text,m.is_outgoing,
               COALESCE(c.title, CAST(m.chat_id AS TEXT)),
               COALESCE(c.chat_type, 'unknown')
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id=m.chat_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
        WHERE TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0)=0
          AND {eligible}
          AND (
              mc.chat_id IS NULL
              OR (
                  NOT EXISTS (
                      SELECT 1 FROM review_queue AS r
                      WHERE r.review_type='message_classification'
                        AND r.status='approved'
                        AND r.subject_type='message'
                        AND r.subject_id=m.message_id
                  )
                  AND (
                      mc.context_stale=1
                      OR (
                          mc.classification_version < ?
                          AND (
                              mc.information_scope='unknown'
                              OR mc.importance IN ('high','critical')
                              OR mc.is_forwarded=1
                              OR (mc.content_type='question' AND mc.actionability='actionable')
                          )
                      )
                  )
              )
          )
        ORDER BY CASE COALESCE(c.chat_type, 'unknown') WHEN 'user' THEN 0 WHEN 'group' THEN 1 ELSE 2 END,
                 COALESCE(m.date, ''), m.message_id
        LIMIT ?
        """,
        (classification_version, limit),
    ).fetchall()
    return [_message_from_row(row) for row in rows]


def history_coverage(conn: sqlite3.Connection, settings: Settings) -> dict[str, int]:
    """Report corpus coverage rather than internal work-window counts."""
    eligible = _eligible_chat_sql(settings)
    total, classified, semantic, private_total, private_classified, private_semantic = (
        conn.execute(
            f"""
            SELECT COUNT(*),
                   SUM(CASE WHEN mc.chat_id IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN a.chat_id IS NOT NULL AND a.batch_id IS NOT NULL AND a.analysis_stale=0 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.chat_type='user' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.chat_type='user' AND mc.chat_id IS NOT NULL THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.chat_type='user' AND a.chat_id IS NOT NULL AND a.batch_id IS NOT NULL AND a.analysis_stale=0 THEN 1 ELSE 0 END)
            FROM messages AS m
            LEFT JOIN chats AS c ON c.chat_id=m.chat_id
            LEFT JOIN message_classifications AS mc ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
            LEFT JOIN ai_message_state AS a ON a.chat_id=m.chat_id AND a.message_id=m.message_id
            WHERE TRIM(COALESCE(m.text, '')) <> ''
              AND COALESCE(m.is_deleted, 0)=0 AND {eligible}
              AND {_semantic_policy_sql()}
            """
        ).fetchone()
    )
    return {
        "eligible": int(total or 0),
        "classified": int(classified or 0),
        "semantic": int(semantic or 0),
        "private_total": int(private_total or 0),
        "private_classified": int(private_classified or 0),
        "private_semantic": int(private_semantic or 0),
    }


def refresh_conversation_analysis_state(conn: sqlite3.Connection, chat_id: int) -> None:
    """Persist chat-level checkpoints derived from committed message state."""
    row = conn.execute(
        """SELECT MAX(m.message_id), MAX(m.date), COUNT(*),
                   SUM(CASE WHEN mc.chat_id IS NULL THEN 0 ELSE 1 END),
                   SUM(CASE WHEN a.chat_id IS NULL OR a.batch_id IS NULL OR a.analysis_stale=1 THEN 0 ELSE 1 END)
           FROM messages AS m
           LEFT JOIN message_classifications AS mc ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
           LEFT JOIN ai_message_state AS a ON a.chat_id=m.chat_id AND a.message_id=m.message_id
           WHERE m.chat_id=? AND TRIM(COALESCE(m.text, ''))<>'' AND COALESCE(m.is_deleted, 0)=0""",
        (chat_id,),
    ).fetchone()
    if not row:
        return
    _, _, total, classified, semantic = row
    now = utc_now()
    conn.execute(
        """INSERT INTO conversation_analysis_state(
               chat_id,covered_until_message_id,covered_until_date,message_count_analyzed,
               classification_complete,semantic_analysis_complete,last_analyzed_at,updated_at
           ) VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(chat_id) DO UPDATE SET
               covered_until_message_id=excluded.covered_until_message_id,
               covered_until_date=excluded.covered_until_date,
               message_count_analyzed=excluded.message_count_analyzed,
               classification_complete=excluded.classification_complete,
               semantic_analysis_complete=excluded.semantic_analysis_complete,
               last_analyzed_at=excluded.last_analyzed_at,
               updated_at=excluded.updated_at""",
        (
            chat_id,
            row[0],
            row[1],
            int(semantic or 0),
            int(total > 0 and int(classified or 0) == int(total)),
            int(total > 0 and int(semantic or 0) == int(total)),
            now,
            now,
        ),
    )


def ensure_daily_jobs(conn: sqlite3.Connection, settings: Settings) -> int:
    """Queue the newest eligible, unprocessed messages as Daily work."""
    pending = fetch_unclassified_messages(
        conn, settings.ai_daily_max_messages, settings, CLASSIFICATION_VERSION
    )
    if pending:
        with conn:
            classify_pending_messages(
                conn, pending, context_version=_context_graph_version(conn)
            )
    cursor = conn.execute(
        "SELECT MAX(date_to) FROM ai_jobs WHERE lane = 'daily' AND status = 'done'"
    ).fetchone()[0]
    messages = fetch_unanalyzed_messages(
        conn,
        settings.ai_daily_max_messages,
        settings,
        exclude_queued_jobs=True,
        after_date=cursor,
    )
    batches = build_ai_batches(messages, settings)
    return _create_jobs(conn, "daily", batches)


def ensure_history_jobs(conn: sqlite3.Connection, settings: Settings) -> int:
    """Create bounded, chat-local chronological windows for history processing."""
    queued = conn.execute(
        """
        SELECT COUNT(*) FROM ai_jobs
        WHERE lane = 'history' AND status IN ('pending', 'running', 'failed')
        """
    ).fetchone()[0]
    available_slots = max(0, settings.history_internal_concurrency - int(queued))
    if not available_slots:
        return 0

    eligible = _eligible_chat_sql(settings)
    candidate_limit = available_slots * settings.history_internal_batch_messages
    rows = conn.execute(
        f"""
        SELECT m.chat_id, m.message_id, m.sender_id, m.date, m.text,
               m.is_outgoing, COALESCE(c.title, CAST(m.chat_id AS TEXT)),
               COALESCE(c.chat_type, 'unknown')
        FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        LEFT JOIN ai_message_state AS a
          ON a.chat_id = m.chat_id AND a.message_id = m.message_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id = m.chat_id AND mc.message_id = m.message_id
        WHERE (a.chat_id IS NULL OR a.analysis_stale=1 OR a.analysis_version < ?)
          AND TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND {eligible}
          AND {_semantic_policy_sql()}
          AND NOT EXISTS (
              SELECT 1 FROM ai_job_messages AS jm
              JOIN ai_jobs AS j ON j.job_id=jm.job_id
              WHERE jm.chat_id=m.chat_id AND jm.message_id=m.message_id
                AND j.status IN ('pending','running','failed')
                AND j.analysis_version=?
          )
        ORDER BY CASE COALESCE(c.chat_type, 'unknown') WHEN 'user' THEN 0 ELSE 1 END,
                 m.chat_id, COALESCE(m.date, ''), m.message_id
        LIMIT ?
        """,
        (ANALYSIS_VERSION, ANALYSIS_VERSION, candidate_limit),
    ).fetchall()
    messages = [_message_from_row(row) for row in rows]
    history_settings = replace(
        settings,
        ai_batch_messages=settings.history_internal_batch_messages,
        ai_batch_chars=settings.history_internal_batch_chars,
    )
    batches = build_ai_batches(messages, history_settings)
    return _create_jobs(conn, "history", batches[:available_slots])


def claim_ai_jobs(
    conn: sqlite3.Connection,
    lane: str,
    limit: int,
    settings: Settings,
    *,
    profile_person_id: int | None = None,
    profile_extractor_version: int | None = None,
) -> list[tuple[int, AIBatch]]:
    rows = conn.execute(
        """
        SELECT job_id FROM ai_jobs
        WHERE lane=? AND analysis_version=? AND status IN ('pending','failed')
          AND ((? IS NULL AND profile_person_id IS NULL) OR profile_person_id=?)
          AND (? IS NULL OR profile_extractor_version=?)
        ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, job_id LIMIT ?
        """,
        (
            lane,
            ANALYSIS_VERSION,
            profile_person_id,
            profile_person_id,
            profile_extractor_version,
            profile_extractor_version,
            limit,
        ),
    ).fetchall()
    claimed: list[tuple[int, AIBatch]] = []
    for (job_id,) in rows:
        with conn:
            cursor = conn.execute(
                """
                UPDATE ai_jobs
                SET status = 'running', attempt_count = attempt_count + 1,
                    started_at = ?
                WHERE job_id = ? AND status IN ('pending', 'failed')
                """,
                (utc_now(), job_id),
            )
        if not cursor.rowcount:
            continue
        batch = _fetch_job_batch(conn, int(job_id), settings)
        if batch is None:
            with conn:
                conn.execute(
                    "UPDATE ai_jobs SET status='superseded',last_error=?,completed_at=? WHERE job_id=?",
                    ("superseded: membership no longer eligible", utc_now(), job_id),
                )
            continue
        try:
            batch = add_contextual_preamble(conn, batch, settings)
            if lane == "history" and settings.ai_context_messages:
                batch = add_history_context(conn, batch, settings)
        except Exception as error:
            with conn:
                conn.execute(
                    """UPDATE ai_jobs SET status='failed',last_error=?
                       WHERE job_id=? AND status='running'""",
                    (
                        f"context assembly: {type(error).__name__}: {error}"[:2000],
                        job_id,
                    ),
                )
            continue
        claimed.append((int(job_id), batch))
    return claimed


def release_ai_job(conn: sqlite3.Connection, job_id: int) -> None:
    with conn:
        conn.execute(
            "UPDATE ai_jobs SET status = 'pending' WHERE job_id = ? AND status = 'running'",
            (job_id,),
        )


def history_queue_counts(
    conn: sqlite3.Connection, settings: Settings
) -> tuple[int, int, int, int]:
    eligible = _eligible_chat_sql(settings)
    pending_messages = conn.execute(
        f"""
        SELECT COUNT(*) FROM messages AS m
        LEFT JOIN chats AS c ON c.chat_id = m.chat_id
        LEFT JOIN ai_message_state AS a ON a.chat_id = m.chat_id AND a.message_id = m.message_id
        WHERE (a.chat_id IS NULL OR a.analysis_stale=1 OR a.analysis_version < ?)
          AND TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0 AND {eligible}
        """,
        (ANALYSIS_VERSION,),
    ).fetchone()[0]
    jobs = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status IN ('pending', 'running') THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
        FROM ai_jobs WHERE lane = 'history'
        """
    ).fetchone()
    return (
        int(pending_messages),
        int(jobs[0] or 0),
        int(jobs[1] or 0),
        int(jobs[2] or 0),
    )


def _create_jobs(conn: sqlite3.Connection, lane: str, batches: list[AIBatch]) -> int:
    if not batches:
        return 0
    now = utc_now()
    created = 0
    with conn:
        for batch in batches:
            ids = [message.message_id for message in batch.messages]
            dates = [message.date for message in batch.messages if message.date]
            fingerprint = hashlib.sha256(
                ",".join(str(message.message_id) for message in batch.messages).encode(
                    "ascii"
                )
            ).hexdigest()
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO ai_jobs (
                    lane, chat_id, first_message_id, last_message_id,
                    date_from, date_to, message_count, analysis_version,
                    selection_fingerprint, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    lane,
                    batch.chat_id,
                    min(ids),
                    max(ids),
                    min(dates) if dates else None,
                    max(dates) if dates else None,
                    len(batch.messages),
                    ANALYSIS_VERSION,
                    fingerprint,
                    now,
                ),
            )
            if cursor.rowcount:
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return an ID for the AI job")
                conn.executemany(
                    "INSERT INTO ai_job_messages(job_id,ordinal,chat_id,message_id) VALUES (?,?,?,?)",
                    [
                        (cursor.lastrowid, ordinal, message.chat_id, message.message_id)
                        for ordinal, message in enumerate(batch.messages)
                    ],
                )
                created += 1
    return created


def _fetch_job_batch(
    conn: sqlite3.Connection, job_id: int, settings: Settings
) -> AIBatch | None:
    rows = conn.execute(
        f"""
        SELECT m.chat_id, m.message_id, m.sender_id, m.date, m.text,
               m.is_outgoing, COALESCE(c.title, CAST(m.chat_id AS TEXT)),
               COALESCE(c.chat_type, 'unknown')
        FROM ai_job_messages AS jm
        JOIN ai_jobs AS j ON j.job_id=jm.job_id
        JOIN messages AS m ON m.chat_id=jm.chat_id AND m.message_id=jm.message_id
        LEFT JOIN chats AS c ON c.chat_id=m.chat_id
        LEFT JOIN message_classifications AS mc
          ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
        WHERE jm.job_id=? AND j.analysis_version=?
          AND TRIM(COALESCE(m.text, '')) <> ''
          AND COALESCE(m.is_deleted, 0) = 0
          AND (
              (j.lane='profile' AND {profile_scan_chat_sql()})
              OR (j.lane <> 'profile' AND {_eligible_chat_sql(settings)})
          )
          AND {_semantic_policy_sql()}
        ORDER BY jm.ordinal
        """,
        (job_id, ANALYSIS_VERSION),
    ).fetchall()
    if not rows:
        return None
    job = conn.execute(
        "SELECT lane,message_count FROM ai_jobs WHERE job_id=?", (job_id,)
    ).fetchone()
    if job is None or len(rows) != int(job[1]):
        return None
    batch_settings = settings
    if job[0] in {"history", "profile"}:
        batch_settings = replace(
            settings,
            ai_batch_messages=settings.history_internal_batch_messages,
            ai_batch_chars=settings.history_internal_batch_chars,
        )
    batches = build_ai_batches([_message_from_row(row) for row in rows], batch_settings)
    if len(batches) != 1:
        return None
    return batches[0] if batches else None


def _message_from_row(row: tuple) -> AIMessage:
    return AIMessage(
        int(row[0]),
        int(row[1]),
        int(row[2]) if row[2] is not None else None,
        row[3],
        row[4] or "",
        bool(row[5]),
        row[6] or str(row[0]),
        row[7] or "unknown",
    )


def save_ai_success(
    conn: sqlite3.Connection,
    batch: AIBatch,
    result: dict | AIAnalysisResult,
    settings: Settings,
    lane: str = "daily",
    job_id: int | None = None,
) -> AISaveResult:
    now = utc_now()
    if isinstance(result, AIAnalysisResult):
        payload = result.as_payload()
        provider = result.provider
        model = result.model
        fallback_used = int(result.fallback_used)
        usage_json = json.dumps(result.usage, ensure_ascii=False)
    else:
        payload = result
        provider = "groq"
        model = settings.groq_model
        fallback_used = 0
        usage_json = None
    try:
        payload = validate_response(payload)
    except ValueError as error:
        with conn:
            conn.execute(
                """INSERT INTO ai_batches(
                       model,created_at,completed_at,message_count,chat_id,error,prompt_chars,
                       response_json,returned_item_count,saved_item_count,rejected_item_count,
                       lane,provider,fallback_used,job_id,usage_json,analysis_version,projection_status
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    model,
                    now,
                    now,
                    len(batch.messages),
                    batch.chat_id,
                    f"validation: {error}",
                    len(batch.prompt),
                    json.dumps(payload, ensure_ascii=False),
                    0,
                    0,
                    1,
                    lane,
                    provider,
                    fallback_used,
                    job_id,
                    usage_json,
                    ANALYSIS_VERSION,
                    "failed",
                ),
            )
            if job_id is not None:
                conn.execute(
                    "UPDATE ai_jobs SET status='failed',last_error=? WHERE job_id=?",
                    (f"validation: {error}"[:2000], job_id),
                )
        return AISaveResult(rejected=1, rejection_reasons=[f"response: {error}"])
    model_items = payload["items"]

    # One transaction guarantees a storage failure does not leave a batch
    # half-marked as analyzed. Individual bad model items are handled below.
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO ai_batches (
                model, created_at, completed_at, message_count,
                chat_id, summary, error, prompt_chars,
                response_json, returned_item_count, saved_item_count,
                rejected_item_count, lane, provider, fallback_used, job_id,
                usage_json, analysis_version, projection_status
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model,
                now,
                now,
                len(batch.messages),
                batch.chat_id,
                payload.get("summary", ""),
                len(batch.prompt),
                json.dumps(payload, ensure_ascii=False),
                len(model_items),
                lane,
                provider,
                fallback_used,
                job_id,
                usage_json,
                ANALYSIS_VERSION,
                "pending",
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an ID for the completed AI batch")
        batch_id = cursor.lastrowid

        valid_refs = {(m.chat_id, m.message_id): m.date for m in batch.messages}
        source_texts = {(m.chat_id, m.message_id): m.text for m in batch.messages}
        profile_authorized_refs: set[tuple[int, int]] | None = None
        profile_person_id: int | None = None
        if lane == "profile":
            row = (
                conn.execute(
                    """SELECT j.profile_person_id,p.telegram_user_id
                       FROM ai_jobs AS j
                       LEFT JOIN people AS p ON p.person_id=j.profile_person_id
                       WHERE j.job_id=?""",
                    (job_id,),
                ).fetchone()
                if job_id is not None
                else None
            )
            person_id = row[0] if row is not None else None
            telegram_user_id = row[1] if row is not None else None
            profile_person_id = int(person_id) if person_id is not None else None
            profile_authorized_refs = {
                (message.chat_id, message.message_id)
                for message in batch.messages
                if telegram_user_id is not None
                and message.sender_id == telegram_user_id
            }

        save_result = AISaveResult(batch_id=batch_id)

        for index, item in enumerate(model_items, start=1):
            normalized, reason = _validate_ai_item(item, valid_refs, source_texts)
            assertion_kind = (
                item.get("assertion_kind", "direct")
                if isinstance(item, dict)
                else "direct"
            )
            source_key = (
                (int(normalized[0]), int(normalized[1]))
                if normalized is not None
                else None
            )
            if (
                reason is None
                and profile_authorized_refs is not None
                and normalized is not None
                and assertion_kind == "direct"
                and source_key not in profile_authorized_refs
            ):
                reason = "profile item source must be authored by the selected person"
            if (
                reason is None
                and profile_authorized_refs is not None
                and assertion_kind == "third_party"
                and source_key in profile_authorized_refs
            ):
                reason = "third-party profile item must cite another participant"
            if (
                reason is None
                and profile_authorized_refs is not None
                and assertion_kind == "inference"
                and not _valid_profile_inference(
                    item, source_key, profile_authorized_refs
                )
            ):
                reason = (
                    "profile inference needs two direct sources and confidence >= 0.85"
                )
            if reason:
                save_result.rejected += 1
                save_result.rejection_reasons.append(f"item {index}: {reason}")
                conn.execute(
                    "INSERT INTO ai_item_rejections(batch_id,item_index,reason,created_at) VALUES (?,?,?,?)",
                    (batch_id, index, reason, now),
                )
                continue
            assert isinstance(item, dict)
            claim_id, claim_inserted, claim_reason = save_claim(
                conn,
                batch_id=int(batch_id),
                claim=legacy_item_claim(item),
                valid_refs=set(valid_refs),
                provider=provider,
                model=model,
                extractor_version=ANALYSIS_VERSION,
                created_at=now,
            )
            if claim_reason:
                raise RuntimeError(
                    "validated AI item could not become a semantic claim: "
                    + claim_reason
                )
            if claim_id is None:
                raise RuntimeError("semantic claim persistence returned no claim ID")
            if profile_person_id is not None:
                conn.execute(
                    """UPDATE semantic_claims SET profile_person_id=?,profile_assertion_kind=?,
                           profile_valid_from=?,profile_valid_to=? WHERE claim_id=?""",
                    (
                        profile_person_id,
                        assertion_kind,
                        item.get("effective_from") if isinstance(item, dict) else None,
                        item.get("effective_to") if isinstance(item, dict) else None,
                        claim_id,
                    ),
                )
            if lane == "profile" and assertion_kind != "direct":
                if claim_inserted:
                    save_result.claims_inserted += 1
                    save_result.saved_claim_ids.append(claim_id)
                else:
                    save_result.claims_duplicated += 1
                continue
            outcome, item_reason = _save_ai_item(
                conn,
                batch_id,
                item,
                valid_refs,
                now,
                source_claim_id=claim_id,
                source_texts=source_texts,
            )
            if item_reason:
                raise RuntimeError(
                    "validated semantic claim could not become a compatibility observation: "
                    + item_reason
                )
            if outcome == "inserted":
                save_result.inserted += 1
                saved_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                save_result.saved_item_ids.append(int(saved_id))
            else:
                save_result.duplicates += 1
            if claim_inserted:
                save_result.claims_inserted += 1
                save_result.saved_claim_ids.append(claim_id)
            else:
                save_result.claims_duplicated += 1

        # Only successful model calls mark these messages as AI-analyzed.
        for message in batch.messages:
            conn.execute(
                """
                INSERT OR REPLACE INTO ai_message_state (
                    chat_id, message_id, batch_id, analysis_version,
                    context_version_used, analysis_stale, analyzed_at, canonicalized_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, NULL)
                """,
                (
                    message.chat_id,
                    message.message_id,
                    batch_id,
                    ANALYSIS_VERSION,
                    _context_graph_version(conn),
                    now,
                ),
            )

        conn.execute(
            """
            UPDATE ai_batches
            SET saved_item_count = ?,
                rejected_item_count = ?
            WHERE batch_id = ?
            """,
            (
                save_result.inserted,
                save_result.rejected,
                batch_id,
            ),
        )

        if job_id is not None:
            conn.execute(
                """
                UPDATE ai_jobs
                SET status = 'done', provider = ?, model = ?,
                    fallback_used = ?, last_error = NULL, completed_at = ?
                WHERE job_id = ?
                """,
                (provider, model, fallback_used, now, job_id),
            )

    return save_result


def save_ai_failure(
    conn: sqlite3.Connection,
    batch: AIBatch,
    error: Exception,
    settings: Settings,
    lane: str = "daily",
    job_id: int | None = None,
) -> None:
    now = utc_now()
    with conn:
        conn.execute(
            """
        INSERT INTO ai_batches (
            model, created_at, completed_at, message_count,
            chat_id, summary, error, prompt_chars,
            response_json, returned_item_count, saved_item_count,
            rejected_item_count, lane, provider, fallback_used, job_id
        )
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL, 0, 0, 0, ?, NULL, 0, ?)
            """,
            (
                settings.groq_model,
                now,
                now,
                len(batch.messages),
                batch.chat_id,
                f"{type(error).__name__}: {error}"[:2000],
                len(batch.prompt),
                lane,
                job_id,
            ),
        )
        if job_id is not None:
            conn.execute(
                """
                UPDATE ai_jobs
                SET status = 'failed', last_error = ?
                WHERE job_id = ?
                """,
                (f"{type(error).__name__}: {error}"[:2000], job_id),
            )


def _save_ai_item(
    conn: sqlite3.Connection,
    batch_id: int,
    item: object,
    valid_refs: dict[tuple[int, int], str | None],
    now: str,
    *,
    source_claim_id: int | None = None,
    source_texts: dict[tuple[int, int], str] | None = None,
) -> tuple[str, str | None]:
    normalized, reason = _validate_ai_item(item, valid_refs, source_texts)
    if reason:
        return "rejected", reason
    assert normalized is not None
    (
        source_chat_id,
        source_message_id,
        title,
        details,
        kind,
        status,
        owner,
        confidence,
        due_date,
        amount,
        person,
        company,
        project_name,
        currency,
    ) = normalized
    source_key = (source_chat_id, source_message_id)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO ai_items (
            batch_id, kind, title, details, status, owner,
            due_date, person, company, project_name, amount, currency, confidence,
            source_chat_id, source_message_id, source_date,
            source_claim_id, created_at, dedupe_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            kind,
            title,
            details,
            status,
            owner,
            due_date,
            person,
            company,
            project_name,
            amount,
            currency,
            confidence,
            source_chat_id,
            source_message_id,
            valid_refs[source_key],
            source_claim_id,
            now,
            _make_dedupe_key(item),
        ),
    )
    if cursor.rowcount:
        return "inserted", None
    if source_claim_id is not None:
        conn.execute(
            "UPDATE ai_items SET source_claim_id=COALESCE(source_claim_id, ?) "
            "WHERE dedupe_key=?",
            (source_claim_id, _make_dedupe_key(item)),
        )
    return "duplicate", None


def _valid_profile_inference(
    item: object,
    source_key: tuple[int, int] | None,
    authorized_refs: set[tuple[int, int]],
) -> bool:
    """Require exact, selected-person evidence before retaining an inference."""
    if not isinstance(item, dict) or float(item["confidence"]) < 0.85:
        return False
    references = item.get("supporting_evidence")
    if not isinstance(references, list):
        return False
    supporting_refs = {
        (reference["source_chat_id"], reference["source_message_id"])
        for reference in references
        if isinstance(reference, dict)
    }
    return (
        len(supporting_refs) >= 2
        and source_key in supporting_refs
        and supporting_refs.issubset(authorized_refs)
    )


_PERSONAL_EVENT_RE = re.compile(
    r"\\b(birthday|anniversary|wedding)\\b|день\\s+рождения|свадьб", re.IGNORECASE
)
_PROJECT_CONTEXT_RE = re.compile(
    r"\\b(project|client|campaign|production|deliverable|film|shoot|brand)\\b|"
    r"проект|клиент|кампан|продакш|съемк|фильм|бренд",
    re.IGNORECASE,
)


def _validate_ai_item(
    item: object,
    valid_refs: dict[tuple[int, int], str | None],
    source_texts: dict[tuple[int, int], str] | None = None,
) -> tuple[tuple | None, str | None]:
    item, contract_error = validate_item_shape(item)
    if contract_error:
        return None, contract_error
    assert item is not None
    try:
        source_chat_id = int(item["source_chat_id"])
        source_message_id = int(item["source_message_id"])
    except (KeyError, TypeError, ValueError):
        return None, "missing or invalid source_chat_id/source_message_id"

    source_key = (source_chat_id, source_message_id)
    if source_key not in valid_refs:
        return (
            None,
            f"source reference {source_chat_id}/{source_message_id} is not in this batch",
        )

    title = item["title"]
    details = item["details"]
    kind = item["kind"]
    status = item["status"]
    owner = item["owner"]
    title = title.strip()
    details = details.strip()
    kind = kind.strip()
    status = status.strip()
    owner = owner.strip()

    confidence = float(item["confidence"])

    if not title:
        return None, "empty title"
    source_text = (source_texts or {}).get(source_key, "")
    if (
        kind == "project"
        and _PERSONAL_EVENT_RE.search(f"{title} {details} {source_text}")
        and not _PROJECT_CONTEXT_RE.search(f"{title} {details} {source_text}")
    ):
        return None, "project item is a personal event without project context"

    due_date, due_date_error = _optional_date(item.get("due_date"))
    if due_date_error:
        return None, due_date_error
    amount, amount_error = _optional_amount(item.get("amount"))
    if amount_error:
        return None, amount_error

    person, person_error = _optional_text(item.get("person"), "person")
    company, company_error = _optional_text(item.get("company"), "company")
    project_name, project_error = _optional_text(
        item.get("project_name"), "project_name"
    )
    currency, currency_error = _optional_text(item.get("currency"), "currency")
    if person_error or company_error or project_error or currency_error:
        return None, person_error or company_error or project_error or currency_error
    return (
        source_chat_id,
        source_message_id,
        title,
        details,
        kind,
        status,
        owner,
        confidence,
        due_date,
        amount,
        person,
        company,
        project_name,
        currency,
    ), None


def _optional_date(value: object) -> tuple[str | None, str | None]:
    if value is None or value == "":
        return None, None
    if not isinstance(value, str):
        return None, "due_date must be YYYY-MM-DD or null"
    try:
        return date.fromisoformat(value).isoformat(), None
    except ValueError:
        return None, "due_date must be YYYY-MM-DD or null"


def _optional_amount(value: object) -> tuple[float | None, str | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "amount must be a finite number or null"
    if not isinstance(value, (int, float, str)):
        return None, "amount must be a finite number or null"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None, "amount must be a finite number or null"
    if not math.isfinite(amount):
        return None, "amount must be a finite number or null"
    return amount, None


def _optional_text(
    value: object,
    field: str,
) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str):
        return None, f"{field} must be text or null"
    return value.strip() or None, None


def _make_dedupe_key(item: object) -> str:
    if not isinstance(item, dict):
        raise ValueError("dedupe requires a mapping item")
    material = "|".join(
        [
            str(item.get("kind", "")),
            str(item.get("title", "")).strip().lower(),
            str(item.get("source_chat_id", "")),
            str(item.get("source_message_id", "")),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
