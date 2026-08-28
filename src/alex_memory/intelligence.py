"""Deterministic operational intelligence: retrieval, follow-ups and health."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone

from .chat_policy import set_chat_policy
from .config import Settings
from .retrieval import SearchResult, retrieve, retrieve_related
from .utils import utc_now

__all__ = ["set_chat_policy"]


def build_context(results: list[SearchResult], settings: Settings) -> str:
    parts: list[str] = []
    size = 0
    for index, item in enumerate(results, start=1):
        line = f"[{index}] {item.citation} | {item.title} | {item.date or 'undated'}\n{item.snippet}\n"
        if size + len(line) > settings.qa_max_context_chars:
            break
        parts.append(line)
        size += len(line)
    return "\n".join(parts)


def answer_question(
    conn: sqlite3.Connection,
    question: str,
    settings: Settings,
    person_id: int | None = None,
) -> tuple[str, list[SearchResult]]:
    results = (
        retrieve_related(conn, "person", person_id, settings, question)
        if person_id is not None
        else retrieve(conn, question, settings)
    )
    if not results:
        return (
            "I couldn't find enough evidence in Alex Memory to answer confidently.",
            [],
        )
    waiting_tasks = [
        r
        for r in results
        if r.result_type == "task" and r.snippet.startswith("WAITING")
    ]
    waiting_question = bool(
        re.search(r"\b(wait|waiting|follow.?up|awaiting)\b|жду|ожида", question, re.I)
    )
    selected = waiting_tasks[:5] if waiting_tasks and waiting_question else results[:5]
    if waiting_tasks:
        lines = ["You are currently waiting on:"]
        for index, item in enumerate(selected, start=1):
            lines.append(
                f"{index}. {item.title} — {item.snippet.removeprefix('WAITING — ').strip()} [{index}]"
            )
    else:
        lines = ["Evidence found in Alex Memory:"]
        for index, item in enumerate(selected, start=1):
            lines.append(f"{index}. {item.title}: {item.snippet[:260]} [{index}]")
    lines.extend(
        [
            "",
            "Sources:",
            *[
                f"[{index}] {item.citation} / {item.date or 'undated'}"
                for index, item in enumerate(selected, start=1)
            ],
        ]
    )
    return "\n".join(lines), selected


async def answer_question_with_ai(
    conn: sqlite3.Connection,
    question: str,
    settings: Settings,
    person_id: int | None = None,
    *,
    router=None,
) -> tuple[str, list[SearchResult]]:
    """Use one routed provider request after bounded local retrieval."""
    baseline, selected = answer_question(conn, question, settings, person_id)
    if not selected or not settings.qa_use_llm:
        return baseline, selected
    # Structured context is canonical state; numbered retrieval evidence is
    # retained separately so the model cannot cite records it never received.
    from .context import ContextRequest, ContextService

    structured = (
        ContextService(conn, settings)
        .builder.build(
            ContextRequest(
                purpose="ask_memory",
                query=question,
                person_ids=[person_id] if person_id is not None else [],
                include_raw_evidence=True,
            )
        )
        .render(min(settings.context_max_chars, settings.qa_max_context_chars // 2))
    )
    # The deterministic fallback has a compact presentation limit. Model
    # evidence instead fills the configured bounded context budget, preserving
    # a balanced retrieval set rather than inheriting a waiting-task shortcut.
    evidence = (
        retrieve_related(conn, "person", person_id, settings, question)
        if person_id is not None
        else retrieve(conn, question, settings)
    )
    evidence = evidence[: settings.qa_max_tasks + settings.qa_max_raw_messages]
    context = build_context(evidence, settings)
    prompt = (
        "Question: "
        + question
        + "\n\nCanonical bounded context:\n"
        + structured
        + "\n\nRetrieved evidence (and the only allowed citation IDs):\n"
        + context
        + "\nAnswer from this evidence only. Label any inference as inference and any suggested action as recommendation. "
        "Cite every factual statement using [n]. If evidence is insufficient, say so plainly."
    )
    try:
        from .ai.router import AIRouter

        answer = await (router or AIRouter(settings, conn=conn)).answer(prompt)
    except Exception:
        # The deterministic answer is deliberately available when routing,
        # configuration, or a provider is unavailable.
        return baseline, selected
    if validate_citations(answer, len(evidence)):
        return answer, evidence
    return baseline, selected


def validate_citations(answer: str, result_count: int) -> bool:
    values = re.findall(r"\[(\d+)\]", answer)
    return bool(values) and all(1 <= int(value) <= result_count for value in values)


def evaluate_follow_ups(
    conn: sqlite3.Connection, settings: Settings, today: date | None = None
) -> int:
    """Reconcile automatic waiting-task reminders without overriding manual state."""
    today = today or date.today()
    cutoff = (today - timedelta(days=settings.follow_up_waiting_after_days)).isoformat()
    rows = conn.execute(
        """SELECT t.task_id,t.title,t.related_person_id,t.related_company_id,t.related_project_id,t.source_chat_id,t.source_item_id,t.updated_at,t.due_date
           FROM tasks t WHERE t.status='waiting' AND substr(t.updated_at,1,10) <= ?""",
        (cutoff,),
    ).fetchall()
    changed = 0
    for task_id, title, person, company, project, chat, _item, updated, due in rows:
        priority = "high" if due and due < today.isoformat() else "normal"
        key = f"waiting-task:{task_id}"
        follow_up = conn.execute(
            """SELECT f.follow_up_id,f.status,f.title,f.priority,f.person_id,
                      f.company_id,f.project_id,f.task_id,f.due_at,
                      f.last_contact_at,f.source_chat_id,
                      EXISTS(
                          SELECT 1 FROM user_feedback AS feedback
                          WHERE feedback.feedback_type='manual_follow_up_status'
                            AND feedback.entity_type='follow_up'
                            AND feedback.entity_id=f.follow_up_id
                      ) AS has_manual_state
               FROM follow_ups AS f WHERE f.dedupe_key=?""",
            (key,),
        ).fetchone()
        proposed = (
            f"Follow up: {title}",
            priority,
            person,
            company,
            project,
            task_id,
            due or today.isoformat(),
            updated,
            chat,
        )
        if follow_up is None:
            conn.execute(
                """INSERT INTO follow_ups(title,status,priority,person_id,company_id,project_id,task_id,reason,due_at,last_contact_at,source_chat_id,source_message_id,confidence,dedupe_key,created_at,updated_at)
                   VALUES (?, 'open', ?, ?, ?, ?, ?, 'waiting task exceeded threshold', ?, ?, ?, NULL, 1.0, ?, ?, ?)""",
                (*proposed, key, utc_now(), utc_now()),
            )
            changed += 1
            _notify(
                conn,
                settings,
                "follow_up_due",
                priority,
                f"Follow up: {title}",
                "Waiting response needs attention.",
                "task",
                task_id,
                key,
            )
            continue
        (
            follow_up_id,
            current_status,
            *current_values,
            has_manual_state,
        ) = follow_up
        if has_manual_state:
            continue
        if current_status == "open" and tuple(current_values) == proposed:
            continue
        now = utc_now()
        conn.execute(
            """UPDATE follow_ups
               SET title=?,status='open',priority=?,person_id=?,company_id=?,
                   project_id=?,task_id=?,due_at=?,last_contact_at=?,
                   source_chat_id=?,resolved_at=NULL,updated_at=?
               WHERE follow_up_id=?""",
            (*proposed, now, follow_up_id),
        )
        changed += 1

    now = utc_now()
    cursor = conn.execute(
        """UPDATE follow_ups AS f
           SET status='cancelled', resolved_at=?, updated_at=?
           WHERE f.status='open'
             AND f.dedupe_key LIKE 'waiting-task:%'
             AND NOT EXISTS (
                 SELECT 1 FROM user_feedback AS feedback
                 WHERE feedback.feedback_type='manual_follow_up_status'
                   AND feedback.entity_type='follow_up'
                   AND feedback.entity_id=f.follow_up_id
             )
             AND NOT EXISTS (
                 SELECT 1 FROM tasks AS t
                 WHERE t.task_id=f.task_id
                   AND t.status='waiting'
                   AND substr(t.updated_at,1,10) <= ?
             )""",
        (now, now, cutoff),
    )
    return changed + cursor.rowcount


def manually_update_follow_up(
    conn: sqlite3.Connection, follow_up_id: int, status: str
) -> bool:
    """Apply an explicit, auditable manual state to one follow-up."""
    if status not in {"open", "snoozed", "done", "cancelled"}:
        raise ValueError("status must be open, snoozed, done, or cancelled")
    row = conn.execute(
        "SELECT status FROM follow_ups WHERE follow_up_id=?", (follow_up_id,)
    ).fetchone()
    if row is None:
        return False
    previous_status = str(row[0])
    if previous_status == status:
        return True
    now = utc_now()
    conn.execute(
        """UPDATE follow_ups
           SET status=?, updated_at=?,
               resolved_at=CASE WHEN ? IN ('done','cancelled') THEN ? ELSE NULL END
           WHERE follow_up_id=?""",
        (status, now, status, now, follow_up_id),
    )
    record_feedback(
        conn,
        "manual_follow_up_status",
        "follow_up",
        follow_up_id,
        {"previous_status": previous_status, "status": status},
    )
    return True


def evaluate_project_health(
    conn: sqlite3.Connection, settings: Settings, today: date | None = None
) -> int:
    today = today or date.today()
    projects = conn.execute(
        "SELECT project_id,canonical_name FROM projects WHERE status NOT IN ('completed','archived')"
    ).fetchall()
    changed = 0
    for project_id, name in projects:
        row = conn.execute(
            """SELECT
                      (
                          SELECT MAX(activity_at) FROM (
                              SELECT COALESCE(item.source_date,task.created_at) AS activity_at
                              FROM tasks AS task
                              LEFT JOIN ai_items AS item ON item.item_id=task.source_item_id
                              WHERE task.related_project_id=?
                              UNION ALL
                              SELECT source_date FROM ai_items WHERE project_id=?
                              UNION ALL
                              SELECT COALESCE(occurred_at,observed_at)
                              FROM context_events WHERE project_id=?
                              UNION ALL
                              SELECT COALESCE(ended_at,started_at)
                              FROM conversation_segments WHERE project_id=?
                          )
                      ),
                      SUM(CASE WHEN status IN ('open','waiting') THEN 1 ELSE 0 END),
                      SUM(CASE WHEN status='waiting' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN due_date IS NOT NULL AND due_date < ? AND status IN ('open','waiting') THEN 1 ELSE 0 END)
               FROM tasks WHERE related_project_id=?""",
            (
                project_id,
                project_id,
                project_id,
                project_id,
                today.isoformat(),
                project_id,
            ),
        ).fetchone()
        last_activity, open_count, waiting_count, overdue = row
        activity_day = (last_activity or "")[:10]
        age = (
            (today - date.fromisoformat(activity_day)).days
            if activity_day
            else settings.project_critical_stale_days
        )
        status = (
            "critical"
            if overdue
            else "stale"
            if not activity_day or age >= settings.project_stale_days
            else "waiting"
            if waiting_count
            else "active"
        )
        score = max(
            0,
            min(
                100,
                100
                - min(age, 30) * 3
                - int(overdue or 0) * 20
                - int(waiting_count or 0) * 8,
            ),
        )
        previous = conn.execute(
            "SELECT status,health_score,last_activity_at FROM projects WHERE project_id=?",
            (project_id,),
        ).fetchone()
        project_changed = previous != (status, score, last_activity)
        if project_changed:
            conn.execute(
                "UPDATE projects SET status=?,health_score=?,last_activity_at=?,updated_at=? WHERE project_id=?",
                (status, score, last_activity, utc_now(), project_id),
            )
            changed += 1
        if project_changed and status in {"stale", "critical"}:
            key = f"project-{status}:{project_id}:{today.isoformat()}"
            _notify(
                conn,
                settings,
                f"project_{status}",
                "critical" if status == "critical" else "high",
                f"Project {status}: {name}",
                f"Last activity {age} days ago; {open_count or 0} open tasks.",
                "project",
                project_id,
                key,
            )
    return changed


def refresh_operational_state(
    conn: sqlite3.Connection,
    settings: Settings,
    today: date | None = None,
) -> tuple[int, int]:
    """Apply deterministic operational projections from existing canonical state."""
    return (
        evaluate_follow_ups(conn, settings, today),
        evaluate_project_health(conn, settings, today),
    )


def attention_items(conn: sqlite3.Connection, settings: Settings) -> list[SearchResult]:
    """Return the current attention view without changing stored state."""
    results: list[SearchResult] = []
    for task_id, title, due, status in conn.execute(
        "SELECT task_id,title,due_date,status FROM tasks WHERE status IN ('open','waiting') AND due_date IS NOT NULL AND due_date <= ? ORDER BY due_date",
        (date.today().isoformat(),),
    ):
        results.append(
            SearchResult(
                "task",
                title,
                f"{status.upper()} — due {due}",
                due,
                100 if due < date.today().isoformat() else 85,
                task_id=task_id,
                source_id=task_id,
            )
        )
    for follow_id, title, priority, due, task_id, chat_id, message_id in conn.execute(
        """SELECT follow_up_id,title,priority,due_at,task_id,source_chat_id,source_message_id
           FROM follow_ups WHERE status='open'
           ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,due_at"""
    ):
        results.append(
            SearchResult(
                "follow-up",
                title,
                priority.upper(),
                due,
                90,
                chat_id=chat_id,
                message_id=message_id,
                task_id=task_id,
                source_id=follow_id,
            )
        )
    for project_id, name, status, score, last in conn.execute(
        "SELECT project_id,canonical_name,status,health_score,last_activity_at FROM projects WHERE status IN ('stale','critical')"
    ):
        results.append(
            SearchResult(
                "project",
                name,
                f"{status.upper()} — health {score if score is not None else '—'}",
                last,
                95 if status == "critical" else 80,
                project_id=project_id,
                source_id=project_id,
            )
        )
    return sorted(results, key=lambda r: r.score, reverse=True)


def profile(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> dict:
    if entity_type == "person":
        from .person_profile import build_person_profile

        return build_person_profile(conn, entity_id)
    table, id_col = {
        "person": ("people", "person_id"),
        "company": ("companies", "company_id"),
        "project": ("projects", "project_id"),
    }[entity_type]
    entity = conn.execute(
        f"SELECT * FROM {table} WHERE {id_col}=?", (entity_id,)
    ).fetchone()
    if not entity:
        return {}
    tasks = conn.execute(
        f"SELECT task_id,title,status,due_date FROM tasks WHERE related_{entity_type}_id=? ORDER BY updated_at DESC LIMIT 20",
        (entity_id,),
    ).fetchall()
    column = {"person": "person_id", "company": "company_id", "project": "project_id"}[
        entity_type
    ]
    memories = conn.execute(
        f"""SELECT title || ': ' || details,source_date FROM ai_items
            WHERE {column}=? ORDER BY source_date DESC,item_id DESC LIMIT 12""",
        (entity_id,),
    ).fetchall()
    data = {"entity": entity, "tasks": tasks, "memories": memories}
    if entity_type == "person":
        data["conversation"] = conn.execute(
            """SELECT current_summary,long_term_summary,last_contact_at,updated_at
               FROM person_context_state WHERE person_id=?""",
            (entity_id,),
        ).fetchone()
        data["open_loops"] = conn.execute(
            """SELECT title,owner,status FROM conversation_open_loops
               WHERE person_id=? AND status IN ('open','waiting')
               ORDER BY updated_at DESC LIMIT 8""",
            (entity_id,),
        ).fetchall()
        data["projects"] = conn.execute(
            """SELECT p.canonical_name,ppc.status,ppc.current_summary
               FROM person_project_context AS ppc JOIN projects AS p ON p.project_id=ppc.project_id
               WHERE ppc.person_id=? ORDER BY ppc.last_activity_at DESC LIMIT 8""",
            (entity_id,),
        ).fetchall()
        data["segments"] = conn.execute(
            """SELECT s.started_at,s.ended_at,p.canonical_name,s.summary
               FROM conversation_contact_segments AS s
               LEFT JOIN projects AS p ON p.project_id=s.primary_project_id
               WHERE s.person_id=? ORDER BY s.started_at DESC LIMIT 8""",
            (entity_id,),
        ).fetchall()
    return data


def record_feedback(
    conn: sqlite3.Connection,
    feedback_type: str,
    entity_type: str | None,
    entity_id: int | None,
    payload: dict,
) -> None:
    conn.execute(
        "INSERT INTO user_feedback(feedback_type,entity_type,entity_id,payload_json,created_at) VALUES (?, ?, ?, ?, ?)",
        (feedback_type, entity_type, entity_id, json.dumps(payload), utc_now()),
    )


def reject_task(conn: sqlite3.Connection, task_id: int) -> bool:
    row = conn.execute(
        "SELECT normalized_title FROM tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    if not row:
        return False
    existing_feedback = conn.execute(
        """SELECT 1 FROM user_feedback WHERE feedback_type='reject_task'
           AND entity_type='task' AND entity_id=? LIMIT 1""",
        (task_id,),
    ).fetchone()
    if existing_feedback is not None:
        return True
    from .operational import manually_update_task

    if not manually_update_task(conn, task_id, "canceled"):
        return False
    record_feedback(conn, "reject_task", "task", task_id, {"normalized_title": row[0]})
    return True


def _notify(
    conn: sqlite3.Connection,
    settings: Settings,
    event_type: str,
    priority: str,
    title: str,
    body: str,
    entity_type: str,
    entity_id: int,
    base_key: str,
) -> None:
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=settings.notification_repeat_hours)).isoformat()
    recent = conn.execute(
        """SELECT 1 FROM notification_outbox
           WHERE dedupe_key LIKE ? AND created_at > ? LIMIT 1""",
        (f"{base_key}:%", cutoff),
    ).fetchone()
    if recent is not None:
        return
    key = f"{base_key}:{now.isoformat()}"
    conn.execute(
        "INSERT OR IGNORE INTO notification_outbox(event_type,priority,title,body,entity_type,entity_id,scheduled_at,status,dedupe_key,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
        (
            event_type,
            priority,
            title,
            body,
            entity_type,
            entity_id,
            now.isoformat(),
            key,
            now.isoformat(),
        ),
    )
