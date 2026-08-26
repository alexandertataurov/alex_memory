"""Bounded, manual historical enrichment for one canonical person profile."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import replace

from rich.console import Console

from .ai.batching import build_ai_batches
from .ai.extraction_contract import ANALYSIS_VERSION
from .ai.repository import _semantic_policy_sql, claim_ai_jobs, profile_scan_chat_sql
from .ai.service import _run_lane
from .config import Settings
from .context.refresh import enqueue_context_invalidations, refresh_pending_context
from .models import AIBatch, AIMessage
from .utils import utc_now

PROFILE_EXTRACTOR_VERSION = 2


def _direct_profile_chat_ids(conn: sqlite3.Connection, person_id: int) -> list[int]:
    """Find direct chats already anchored by this person's canonical evidence."""
    rows = conn.execute(
        """SELECT DISTINCT linked.chat_id FROM (
             SELECT source_chat_id AS chat_id FROM ai_items WHERE person_id=?
             UNION SELECT source_chat_id FROM tasks WHERE related_person_id=?
             UNION SELECT source_chat_id FROM context_events WHERE person_id=?
             UNION SELECT source_chat_id FROM context_facts WHERE subject_type='person' AND subject_id=?
             UNION SELECT source_chat_id FROM relationships WHERE (from_type='person' AND from_id=?) OR (to_type='person' AND to_id=?)
           ) AS linked JOIN chats AS c ON c.chat_id=linked.chat_id
           WHERE linked.chat_id IS NOT NULL AND c.chat_type='user'""",
        (person_id, person_id, person_id, person_id, person_id, person_id),
    ).fetchall()
    return [int(row[0]) for row in rows]


def profile_scan_status(
    conn: sqlite3.Connection, person_id: int, *, include_eligibility: bool = True
) -> dict[str, int | str | bool | None]:
    row = conn.execute(
        """SELECT SUM(status='done'),SUM(status='pending'),SUM(status='running'),SUM(status='failed'),
                  SUM(CASE WHEN status='done' THEN message_count ELSE 0 END),
                  SUM(CASE WHEN status='pending' THEN message_count ELSE 0 END),
                  SUM(CASE WHEN status='running' THEN message_count ELSE 0 END),
                  SUM(CASE WHEN status='failed' THEN message_count ELSE 0 END),
                  MAX(completed_at),MAX(profile_extractor_version)
           FROM ai_jobs
           WHERE profile_person_id=? AND profile_extractor_version=?""",
        (person_id, PROFILE_EXTRACTOR_VERSION),
    ).fetchone()
    direct: bool | None = None
    eligible: int | None = None
    if include_eligibility:
        direct = bool(
            conn.execute(
                """SELECT 1 FROM people AS p JOIN chats AS c ON c.chat_id=p.telegram_user_id
                   WHERE p.person_id=? AND c.chat_type='user'""",
                (person_id,),
            ).fetchone()
        )
        chat_ids = _direct_profile_chat_ids(conn, person_id)
        marks = ",".join("?" for _ in chat_ids) or "NULL"
        eligible_sql = f"""SELECT DISTINCT m.chat_id,m.message_id FROM messages AS m JOIN people AS p ON p.person_id=?
               JOIN chats AS c ON c.chat_id=m.chat_id
               LEFT JOIN message_classifications AS mc
                 ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
               WHERE (m.chat_id IN ({marks}) OR m.chat_id=p.telegram_user_id OR m.sender_id=p.telegram_user_id
                 OR EXISTS (
                     SELECT 1 FROM semantic_claim_evidence AS e
                     JOIN semantic_claim_entity_refs AS r ON r.claim_id=e.claim_id
                     WHERE e.source_chat_id=m.chat_id AND e.source_message_id=m.message_id
                       AND r.entity_type='person' AND r.canonical_entity_id=?
                       AND r.resolution_status='resolved'))
                 AND p.telegram_user_id IS NOT NULL
                 AND TRIM(COALESCE(m.text,''))<>'' AND COALESCE(m.is_deleted,0)=0
                 AND {profile_scan_chat_sql()} AND {_semantic_policy_sql()}"""
        params = (person_id, *chat_ids, person_id)
        eligible = conn.execute(
            f"SELECT COUNT(*) FROM ({eligible_sql})", params
        ).fetchone()[0]
        processed = conn.execute(
            f"""SELECT COUNT(*) FROM ({eligible_sql}) AS eligible
                 WHERE EXISTS (
                    SELECT 1 FROM ai_job_messages AS membership
                    JOIN ai_jobs AS job ON job.job_id=membership.job_id
                    WHERE membership.chat_id=eligible.chat_id
                      AND membership.message_id=eligible.message_id
                      AND job.profile_person_id=? AND job.status='done'
                      AND job.profile_extractor_version=?
                 )""",
            (*params, person_id, PROFILE_EXTRACTOR_VERSION),
        ).fetchone()[0]
        direct = bool(direct or chat_ids)
    return {
        "done": int(row[0] or 0),
        "pending": int(row[1] or 0),
        "running": int(row[2] or 0),
        "failed": int(row[3] or 0),
        # Kept as a compatibility field for existing callers; it is now a
        # distinct eligible-evidence count rather than a sum of job windows.
        "completed_messages": int(processed or 0),
        "processed_messages": int(processed or 0),
        "pending_messages": int(row[5] or 0),
        "running_messages": int(row[6] or 0),
        "failed_messages": int(row[7] or 0),
        "last_completed_at": row[8],
        "extractor_version": int(row[9] or PROFILE_EXTRACTOR_VERSION),
        "direct_chat_available": direct,
        "eligible_messages": int(eligible or 0) if eligible is not None else None,
    }


def profile_scan_debug(conn: sqlite3.Connection, person_id: int) -> dict:
    """Return bounded, metadata-only Deep Scan diagnostics for one person.

    This is an audit read over the durable job, validation, and claim records;
    it deliberately does not retain or display message text.
    """
    counts = conn.execute(
        """SELECT
             SUM(profile_assertion_kind='direct'),
             SUM(profile_assertion_kind='third_party'),
             SUM(profile_assertion_kind='inference')
           FROM semantic_claims WHERE profile_person_id=?""",
        (person_id,),
    ).fetchone()
    rejected = conn.execute(
        """SELECT COUNT(*) FROM ai_item_rejections AS r
           JOIN ai_batches AS b ON b.batch_id=r.batch_id
           JOIN ai_jobs AS j ON j.job_id=b.job_id
           WHERE j.profile_person_id=? AND j.profile_extractor_version=?""",
        (person_id, PROFILE_EXTRACTOR_VERSION),
    ).fetchone()[0]
    rejection_reasons = conn.execute(
        """SELECT r.reason,COUNT(*) AS rejected_count FROM ai_item_rejections AS r
           JOIN ai_batches AS b ON b.batch_id=r.batch_id
           JOIN ai_jobs AS j ON j.job_id=b.job_id
           WHERE j.profile_person_id=? AND j.profile_extractor_version=? GROUP BY r.reason
           ORDER BY rejected_count DESC,r.reason ASC LIMIT 3""",
        (person_id, PROFILE_EXTRACTOR_VERSION),
    ).fetchall()
    jobs = conn.execute(
        """SELECT j.job_id,j.status,j.message_count,j.attempt_count,j.started_at,j.completed_at,
                  b.provider,b.model,
                  CASE WHEN COALESCE(j.last_error,b.error,'') <> '' THEN 1 ELSE 0 END
           FROM ai_jobs AS j LEFT JOIN ai_batches AS b ON b.job_id=j.job_id
           WHERE j.profile_person_id=? AND j.profile_extractor_version=?
           ORDER BY j.job_id DESC LIMIT 5""",
        (person_id, PROFILE_EXTRACTOR_VERSION),
    ).fetchall()
    return {
        "direct_claims": int(counts[0] or 0),
        "third_party_claims": int(counts[1] or 0),
        "inference_claims": int(counts[2] or 0),
        "rejected_items": int(rejected or 0),
        "rejection_reasons": [
            (_profile_rejection_label(str(row[0])), int(row[1]))
            for row in rejection_reasons
        ],
        "jobs": [tuple(row) for row in jobs],
    }


def _profile_rejection_label(reason: str) -> str:
    """Keep operator diagnostics useful without displaying unstable validator prose."""
    if reason == "profile item source must be authored by the selected person":
        return "direct claim cited the wrong speaker"
    if reason == "third-party profile item must cite another participant":
        return "third-party claim cited the selected person"
    if reason.startswith("profile inference needs two direct sources"):
        return "inference lacks two direct sources"
    if reason.startswith("invalid status"):
        return "unsupported task status"
    return "other local validation rejection"


def queue_profile_scan(
    conn: sqlite3.Connection, settings: Settings, person_id: int, *, limit: int = 2
) -> int:
    """Persist bounded chronological direct-conversation and self-authored windows."""
    if limit < 1:
        raise ValueError("profile scan limit must be positive")
    person = conn.execute(
        "SELECT telegram_user_id FROM people WHERE person_id=?", (person_id,)
    ).fetchone()
    if person is None or person[0] is None:
        return 0
    chat_ids = _direct_profile_chat_ids(conn, person_id)
    marks = ",".join("?" for _ in chat_ids) or "NULL"
    rows = conn.execute(
        f"""SELECT m.chat_id,m.message_id,m.sender_id,m.date,m.text,m.is_outgoing,
                  COALESCE(c.title,CAST(m.chat_id AS TEXT)),COALESCE(c.chat_type,'unknown')
               FROM messages AS m JOIN chats AS c ON c.chat_id=m.chat_id
               LEFT JOIN message_classifications AS mc
                 ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
               WHERE (m.chat_id IN ({marks}) OR m.chat_id=? OR m.sender_id=?
                 OR EXISTS (
                     SELECT 1 FROM semantic_claim_evidence AS e
                     JOIN semantic_claim_entity_refs AS r ON r.claim_id=e.claim_id
                     WHERE e.source_chat_id=m.chat_id AND e.source_message_id=m.message_id
                       AND r.entity_type='person' AND r.canonical_entity_id=?
                       AND r.resolution_status='resolved')) AND TRIM(COALESCE(m.text,''))<>''
                 AND COALESCE(m.is_deleted,0)=0 AND {profile_scan_chat_sql()} AND {_semantic_policy_sql()} AND NOT EXISTS (
                     SELECT 1 FROM ai_job_messages jm JOIN ai_jobs j ON j.job_id=jm.job_id
                     WHERE jm.chat_id=m.chat_id AND jm.message_id=m.message_id
                   AND j.profile_person_id=? AND j.profile_extractor_version=?)
           ORDER BY m.chat_id,m.date,m.message_id""",
        (
            *chat_ids,
            person[0],
            person[0],
            person_id,
            person_id,
            PROFILE_EXTRACTOR_VERSION,
        ),
    ).fetchall()
    bounded = replace(
        settings,
        ai_batch_messages=settings.history_internal_batch_messages,
        ai_batch_chars=settings.history_internal_batch_chars,
    )
    batches = build_ai_batches(
        [
            AIMessage(
                int(row[0]),
                int(row[1]),
                row[2],
                row[3],
                row[4] or "",
                bool(row[5]),
                row[6],
                row[7],
            )
            for row in rows
        ],
        bounded,
    )[:limit]
    created = 0
    with conn:
        for batch in batches:
            ids = [message.message_id for message in batch.messages]
            dates = [message.date for message in batch.messages if message.date]
            fingerprint = hashlib.sha256(
                (
                    f"profile:{person_id}:{PROFILE_EXTRACTOR_VERSION}:"
                    + ",".join(map(str, ids))
                ).encode("ascii")
            ).hexdigest()
            cursor = conn.execute(
                """INSERT OR IGNORE INTO ai_jobs(lane,chat_id,first_message_id,last_message_id,date_from,date_to,message_count,analysis_version,selection_fingerprint,status,profile_person_id,profile_extractor_version,created_at)
                   VALUES ('profile',?,?,?,?,?,?,?,?, 'pending',?,?,?)""",
                (
                    batch.chat_id,
                    min(ids),
                    max(ids),
                    min(dates) if dates else None,
                    max(dates) if dates else None,
                    len(ids),
                    ANALYSIS_VERSION,
                    fingerprint,
                    person_id,
                    PROFILE_EXTRACTOR_VERSION,
                    utc_now(),
                ),
            )
            if cursor.rowcount and cursor.lastrowid is not None:
                conn.executemany(
                    "INSERT INTO ai_job_messages(job_id,ordinal,chat_id,message_id) VALUES (?,?,?,?)",
                    [
                        (cursor.lastrowid, ordinal, message.chat_id, message.message_id)
                        for ordinal, message in enumerate(batch.messages)
                    ],
                )
                created += 1
    return created


async def enrich_person(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    person_id: int,
    *,
    limit: int = 2,
    live_progress: Callable[[], None] | None = None,
    render_console: bool = True,
) -> dict[str, int | str | None]:
    """Run a bounded manual scan through the normal validated extraction path."""
    status = profile_scan_status(conn, person_id)
    # Process an existing backlog before creating more jobs. The old Textual
    # queue-only action could leave many pending windows; adding two more on
    # every resume made that backlog appear never-ending.
    pending = status["pending"]
    created = (
        0
        if isinstance(pending, int) and pending > 0
        else queue_profile_scan(conn, settings, person_id, limit=limit)
    )
    jobs = claim_ai_jobs(
        conn,
        "profile",
        limit,
        settings,
        profile_person_id=person_id,
        profile_extractor_version=PROFILE_EXTRACTOR_VERSION,
    )
    await _process_profile_jobs(
        conn,
        settings,
        console,
        person_id,
        jobs,
        created,
        live_progress=live_progress,
        render_console=render_console,
    )
    result = profile_scan_status(conn, person_id)
    result["queued"] = created
    result["outcome"] = (
        "No canonically owned direct conversation is available to scan."
        if not result["direct_chat_available"]
        else f"Deep Scan could not complete {result['failed']} window(s); they remain retryable."
        if result["failed"]
        else "No eligible unscanned messages remain."
        if not created and not jobs
        else f"Deep Scan processed {len(jobs)} bounded window(s); {created} new window(s) were queued."
    )
    return result


async def drain_queued_profile_scan(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    person_id: int,
    *,
    max_windows: int = 64,
    live_progress: Callable[[], None] | None = None,
    render_console: bool = True,
) -> dict[str, int | str | None]:
    """Process a bounded existing backlog without expanding it or retrying failures."""
    if max_windows < 1:
        raise ValueError("max_windows must be positive")
    processed = 0
    while processed < max_windows:
        pending = conn.execute(
            "SELECT COUNT(*) FROM ai_jobs WHERE lane='profile' AND profile_person_id=? AND status='pending'",
            (person_id,),
        ).fetchone()[0]
        if not pending:
            break
        jobs = claim_ai_jobs(
            conn,
            "profile",
            min(2, max_windows - processed),
            settings,
            profile_person_id=person_id,
            profile_extractor_version=PROFILE_EXTRACTOR_VERSION,
        )
        if not jobs:
            break
        await _process_profile_jobs(
            conn,
            settings,
            console,
            person_id,
            jobs,
            created=0,
            live_progress=live_progress,
            render_console=render_console,
        )
        processed += len(jobs)
    result = profile_scan_status(conn, person_id)
    result["processed"] = processed
    result["outcome"] = (
        f"Processed {processed} queued window(s); {result['pending']} remain ready."
        if processed
        else "No queued Deep Scan windows are ready to process."
    )
    return result


async def _process_profile_jobs(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    person_id: int,
    jobs: list[tuple[int, AIBatch]],
    created: int,
    *,
    live_progress: Callable[[], None] | None = None,
    render_console: bool = True,
) -> None:
    """Submit already-claimed person jobs through the one profile worker path."""
    name = conn.execute(
        "SELECT canonical_name FROM people WHERE person_id=?", (person_id,)
    ).fetchone()
    prepared = []
    for job_id, batch in jobs:
        prompt = (
            f"Person Profile Deep Scan for {name[0] if name else person_id}. "
            "For each item include assertion_kind (direct, third_party, or inference) "
            "and effective_from/effective_to as YYYY-MM-DD or null. Use direct only for "
            "the selected person's own statement, third_party for another participant's "
            "attributed statement, and inference only when two direct statements support it. "
            "Use important_fact titles with a stable category prefix such as identity.email, "
            "professional.role, capability.skill, personal.interest, relationship.history, "
            "or connection.organization. Extract only evidence-backed profile facts, "
            "commitments, events, and temporal changes. Every item must cite a submitted "
            f"message about {name[0] if name else 'the selected person'}.\n\n{batch.prompt}"
        )
        prepared.append(
            (job_id, AIBatch(batch.chat_id, batch.chat_title, batch.messages, prompt))
        )
    if prepared:
        await _run_lane(
            conn,
            settings,
            console,
            "profile",
            prepared,
            created,
            render_console=render_console,
            on_progress=live_progress,
        )
        batch_rows = conn.execute(
            "SELECT batch_id FROM ai_batches WHERE job_id IN (%s) AND projection_status='completed'"
            % ",".join("?" for job_id, _ in prepared),
            [job_id for job_id, _ in prepared],
        ).fetchall()
        for (batch_id,) in batch_rows:
            enqueue_context_invalidations(conn, int(batch_id), {("person", person_id)})
        if batch_rows:
            await refresh_pending_context(conn, settings)
