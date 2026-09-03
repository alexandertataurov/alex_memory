"""Read-only AI result queries for terminal diagnostics and analytics."""

from __future__ import annotations

import sqlite3


def fetch_ai_router_diagnostics(
    conn: sqlite3.Connection,
) -> tuple[list[tuple], list[tuple]]:
    """Return aggregate quota state and recent decisions without prompt content."""
    usage = conn.execute(
        """SELECT model_key,provider,model,attempt_count,success_count,
                  estimated_input_tokens,actual_input_tokens,output_tokens,
                  cooldown_until,last_error
           FROM ai_model_usage WHERE usage_date=date('now') ORDER BY model_key"""
    ).fetchall()
    decisions = conn.execute(
        """SELECT workload,priority,provider,model,outcome,decision_reason,error,created_at
           FROM ai_route_events ORDER BY event_id DESC LIMIT 12"""
    ).fetchall()
    return usage, decisions


def fetch_ai_request_monitor(
    conn: sqlite3.Connection,
) -> tuple[tuple, list[tuple], list[tuple], list[tuple]]:
    """Return live job state and recent provider outcomes for the terminal monitor."""
    job_counts = conn.execute(
        """SELECT
               COALESCE(SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN status='running' THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0)
           FROM ai_jobs"""
    ).fetchone()
    recent_totals = conn.execute(
        """SELECT
               COUNT(*),
               COALESCE(SUM(message_count), 0),
               COALESCE(SUM(fallback_used), 0),
               COALESCE(SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END), 0)
           FROM ai_batches
           WHERE julianday(completed_at) >= julianday('now') - (1.0 / 24.0)"""
    ).fetchone()
    provider_totals = conn.execute(
        """SELECT COALESCE(provider,'router'),COUNT(*),COALESCE(SUM(fallback_used),0)
           FROM ai_batches
           WHERE julianday(completed_at) >= julianday('now') - (1.0 / 24.0)
           GROUP BY COALESCE(provider,'router')"""
    ).fetchall()
    active_jobs = conn.execute(
        """SELECT j.lane,COALESCE(c.title,CAST(j.chat_id AS TEXT)),j.message_count,
                  j.status,COALESCE(j.provider,'router'),j.model,j.attempt_count,j.last_error
           FROM ai_jobs AS j
           LEFT JOIN chats AS c ON c.chat_id=j.chat_id
           WHERE j.status IN ('pending','running')
           ORDER BY CASE j.status WHEN 'running' THEN 0 ELSE 1 END,j.created_at
           LIMIT 12"""
    ).fetchall()
    recent_requests = conn.execute(
        """SELECT b.lane,COALESCE(c.title,CAST(b.chat_id AS TEXT)),b.message_count,
                  COALESCE(b.provider,'router'),b.model,b.fallback_used,b.error,
                  COALESCE(j.status,CASE WHEN b.error IS NULL THEN 'done' ELSE 'failed' END),
                  b.completed_at,json_extract(b.usage_json,'$.fallback_reason')
           FROM ai_batches AS b
           LEFT JOIN chats AS c ON c.chat_id=b.chat_id
           LEFT JOIN ai_jobs AS j ON j.job_id=b.job_id
           ORDER BY b.batch_id DESC
           LIMIT 10"""
    ).fetchall()
    return (*job_counts, *recent_totals), provider_totals, active_jobs, recent_requests


def fetch_findings(conn: sqlite3.Connection, limit: int = 60) -> list[tuple]:
    return conn.execute(
        """
        SELECT
            i.kind, i.status, i.owner, i.due_date, i.title, i.details,
            i.person, i.company, i.confidence,
            COALESCE(c.title, CAST(i.source_chat_id AS TEXT)), i.source_date
        FROM ai_items AS i
        LEFT JOIN chats AS c ON c.chat_id = i.source_chat_id
        WHERE COALESCE(c.is_bot, 0) = 0
          AND (i.kind <> 'important_fact' OR (
              LOWER(i.title) NOT LIKE '%login code%'
              AND LOWER(i.title) NOT LIKE '%verification code%'
              AND LOWER(i.title) NOT LIKE '%security code%'
              AND LOWER(i.title) NOT LIKE '%one-time code%'
          ))
        ORDER BY
            CASE WHEN i.status IN ('open', 'waiting', 'blocked') THEN 0 ELSE 1 END,
            CASE WHEN i.due_date IS NULL THEN 1 ELSE 0 END,
            i.due_date, COALESCE(i.source_date, '') DESC, i.item_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def fetch_last_batch_diagnostics(
    conn: sqlite3.Connection, limit: int = 20
) -> list[tuple]:
    return conn.execute(
        """
        SELECT
            b.batch_id, b.lane, COALESCE(c.title, CAST(b.chat_id AS TEXT)),
            b.message_count, COALESCE(b.provider, 'router'), b.model,
            b.fallback_used, b.summary, b.returned_item_count,
            b.saved_item_count, b.rejected_item_count, b.error,
            COALESCE(j.status, CASE WHEN b.error IS NULL THEN 'done' ELSE 'failed' END),
            b.completed_at
        FROM ai_batches AS b
        LEFT JOIN chats AS c ON c.chat_id = b.chat_id
        LEFT JOIN ai_jobs AS j ON j.job_id = b.job_id
        ORDER BY b.batch_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def ai_lane_stats(
    conn: sqlite3.Connection, lane: str
) -> tuple[int, int, int, str | None, int]:
    """Return pending, done, failed, last-success, and today's message count."""
    counts = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status IN ('pending', 'running') THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
        FROM ai_jobs WHERE lane = ?
        """,
        (lane,),
    ).fetchone()
    last_success = conn.execute(
        "SELECT MAX(completed_at) FROM ai_jobs WHERE lane = ? AND status = 'done'",
        (lane,),
    ).fetchone()[0]
    today_count = conn.execute(
        """
        SELECT COALESCE(SUM(message_count), 0)
        FROM ai_batches
        WHERE lane = ? AND error IS NULL AND date(completed_at) = date('now')
        """,
        (lane,),
    ).fetchone()[0]
    return (
        int(counts[0] or 0),
        int(counts[1] or 0),
        int(counts[2] or 0),
        last_success,
        int(today_count or 0),
    )


def fetch_ai_analytics(
    conn: sqlite3.Connection,
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Return compact, source-backed data for the terminal analytics screen."""
    provider_rows = conn.execute(
        """
        SELECT
            lane, COALESCE(provider, 'groq') AS provider, COUNT(*) AS batches,
            COALESCE(SUM(message_count), 0) AS messages,
            COALESCE(SUM(returned_item_count), 0) AS returned,
            COALESCE(SUM(saved_item_count), 0) AS saved,
            COALESCE(SUM(rejected_item_count), 0) AS rejected,
            COALESCE(SUM(fallback_used), 0) AS fallbacks,
            COALESCE(SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END), 0) AS failures
        FROM ai_batches
        GROUP BY lane, COALESCE(provider, 'groq')
        ORDER BY lane, batches DESC
        """
    ).fetchall()
    item_rows = conn.execute(
        """
        SELECT kind, status, COUNT(*)
        FROM ai_items
        GROUP BY kind, status
        ORDER BY COUNT(*) DESC, kind, status
        """
    ).fetchall()
    error_rows = conn.execute(
        """
        SELECT lane, COALESCE(provider, 'router'), error, completed_at
        FROM ai_batches
        WHERE error IS NOT NULL
        ORDER BY batch_id DESC
        LIMIT 5
        """
    ).fetchall()
    return provider_rows, item_rows, error_rows
