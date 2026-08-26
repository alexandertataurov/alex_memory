from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable

from ...config import Settings
from ...context.models import BuiltContext
from ...schema_support import fts5_available
from .models import EvidenceItem


_STOP_WORDS = {
    "about",
    "after",
    "again",
    "and",
    "are",
    "for",
    "from",
    "have",
    "into",
    "need",
    "that",
    "the",
    "this",
    "with",
    "will",
    "your",
    "send",
    "structure",
}
_DOMAIN_TERMS = {
    "hedge": (
        "hedge",
        "hedging",
        "fx",
        "forward",
        "spread",
        "pricing",
        "rate",
        "difference",
    ),
    "hedging": (
        "hedge",
        "hedging",
        "fx",
        "forward",
        "spread",
        "pricing",
        "rate",
        "difference",
    ),
    "tbc": ("tbc", "fx", "spread", "pricing", "rate"),
    "flow": ("flow", "funds", "flow-of-funds"),
    "funds": ("flow", "funds", "flow-of-funds"),
}


def task_concepts(
    task: dict, context: BuiltContext, extra: Iterable[str] = ()
) -> list[str]:
    """Expand only explicit task/entity terms and small auditable domain maps."""
    words = re.findall(
        r"[a-z0-9][a-z0-9_-]{1,}",
        f"{task['title']} {task.get('details') or ''}".casefold(),
    )
    concepts = [word for word in words if word not in _STOP_WORDS]
    for entity in (*context.people, *context.projects, *context.companies):
        concepts.extend(
            re.findall(
                r"[a-z0-9][a-z0-9_-]{1,}",
                str(entity.get("canonical_name", "")).casefold(),
            )
        )
    for concept in list(concepts):
        concepts.extend(_DOMAIN_TERMS.get(concept, ()))
    concepts.extend(value.casefold().strip() for value in extra if value.strip())
    return _unique(concepts)


def structured_evidence(task: dict, context: BuiltContext) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for event_record in context.events:
        if event_record.get("task_id") not in (
            None,
            task["task_id"],
        ) and not _event_matches_task(event_record, task):
            continue
        evidence.append(
            EvidenceItem(
                f"E-event-{event_record['event_id']}",
                "event",
                event_record.get("title") or event_record["event_type"],
                event_record.get("description") or "",
                event_record.get("occurred_at") or event_record.get("updated_at"),
                event_record.get("source_chat_id"),
                event_record.get("source_message_id"),
                float(event_record.get("score", 0)),
                event_record.get("confidence"),
                ["canonical event linked through task context"],
            )
        )
    for fact in context.facts:
        value = fact.get("value")
        if isinstance(value, dict):
            value = ", ".join(f"{key}={item}" for key, item in value.items())
        evidence.append(
            EvidenceItem(
                f"E-fact-{fact['fact_id']}",
                "fact",
                str(fact.get("predicate", "fact")),
                str(value or ""),
                fact.get("valid_from") or fact.get("updated_at"),
                fact.get("source_chat_id"),
                fact.get("source_message_id"),
                float(fact.get("score", 0)),
                fact.get("confidence"),
                ["current temporal fact in task context"],
            )
        )
    for event in _task_events(task, context):
        evidence.append(event)
    return evidence


def raw_message_evidence(
    conn: sqlite3.Connection,
    task: dict,
    context: BuiltContext,
    concepts: list[str],
    settings: Settings,
    *,
    as_of: str,
    max_messages: int | None = None,
) -> tuple[list[EvidenceItem], dict]:
    """Search FTS first, then validate every hit against task anchors locally."""
    limit = max_messages or settings.task_deep_dive_max_raw_messages
    queries = concepts[: settings.task_deep_dive_max_queries_per_round]
    rows: dict[tuple[int, int], tuple] = {}
    diagnostics = {
        "fts_queries": 0,
        "fallback_queries": 0,
        "raw_candidates": 0,
        "raw_rejected": 0,
    }
    fts_available = fts5_available(conn)
    for term in queries:
        if len(term) < 2:
            continue
        if fts_available:
            fetched = _fts_messages(conn, term, as_of, limit)
            diagnostics["fts_queries"] += 1
        else:
            diagnostics["fallback_queries"] += 1
            fetched = _like_messages(conn, term, as_of, limit)
        for row in fetched:
            rows[(int(row[0]), int(row[1]))] = row
    anchors = _anchors(task, context)
    related_chats = _related_chats(conn, task, context, as_of)
    selected: list[EvidenceItem] = []
    for row in rows.values():
        diagnostics["raw_candidates"] += 1
        chat_id, message_id, date, text, sender_id, title = row
        body = str(text or "")
        lowered = body.casefold()
        concept_hits = len(
            {term for term in concepts if len(term) > 1 and term in lowered}
        )
        anchor_hits = len({anchor for anchor in anchors if anchor in lowered})
        direct_source = chat_id == task.get("source_chat_id")
        related_chat = chat_id in related_chats
        eligible = (
            anchor_hits > 0
            or (related_chat and concept_hits >= 2)
            or (direct_source and concept_hits >= 1)
        )
        if not eligible:
            diagnostics["raw_rejected"] += 1
            continue
        score = (
            20
            + concept_hits * 10
            + anchor_hits * 25
            + (25 if direct_source else 0)
            + (12 if related_chat else 0)
        )
        reasons = []
        if anchor_hits:
            reasons.append("mentions a task-linked entity")
        if related_chat and concept_hits >= 2:
            reasons.append("graph-related chat with multiple task concepts")
        if direct_source:
            reasons.append("task source chat")
        selected.append(
            EvidenceItem(
                f"E-message-{chat_id}-{message_id}",
                "message",
                str(title or f"Chat {chat_id}"),
                body,
                date,
                int(chat_id),
                int(message_id),
                float(score),
                None,
                reasons,
                _conversation_window(
                    conn, int(chat_id), int(message_id), settings, as_of
                ),
            )
        )
    selected.sort(
        key=lambda item: (
            -item.relevance_score,
            item.occurred_at or "",
            item.evidence_id,
        )
    )
    return selected[:limit], diagnostics


def _task_events(task: dict, context: BuiltContext) -> list[EvidenceItem]:
    # ContextBuilder does not read lifecycle events. The calling service augments this
    # through its connection-specific helper; retained for a stable structured shape.
    return []


def lifecycle_evidence(
    conn: sqlite3.Connection, task_id: int, as_of: str
) -> list[EvidenceItem]:
    rows = conn.execute(
        """SELECT event_id,event_type,source,payload_json,created_at FROM task_events
           WHERE task_id=? AND created_at<=? ORDER BY created_at ASC LIMIT 40""",
        (task_id, as_of),
    ).fetchall()
    return [
        EvidenceItem(
            f"E-task-event-{row[0]}",
            "task_event",
            str(row[1]),
            str(row[3] or row[2]),
            str(row[4]),
            None,
            None,
            65.0,
            None,
            ["task lifecycle audit event"],
        )
        for row in rows
    ]


def _fts_messages(
    conn: sqlite3.Connection, term: str, as_of: str, limit: int
) -> list[tuple]:
    return conn.execute(
        """SELECT m.chat_id,m.message_id,m.date,m.text,m.sender_id,c.title
               FROM messages_fts f JOIN messages m ON m.chat_id=f.chat_id AND m.message_id=f.message_id
               LEFT JOIN chats c ON c.chat_id=m.chat_id
               WHERE f.text MATCH ? AND m.date<=? AND m.is_deleted=0
               ORDER BY m.date DESC LIMIT ?""",
        (f'"{term.replace('"', "")}"', as_of, limit),
    ).fetchall()


def _like_messages(
    conn: sqlite3.Connection, term: str, as_of: str, limit: int
) -> list[tuple]:
    return conn.execute(
        """SELECT m.chat_id,m.message_id,m.date,m.text,m.sender_id,c.title
           FROM messages m LEFT JOIN chats c ON c.chat_id=m.chat_id
           WHERE LOWER(COALESCE(m.text,'')) LIKE ? AND m.date<=? AND m.is_deleted=0
           ORDER BY m.date DESC LIMIT ?""",
        (f"%{term.casefold()}%", as_of, limit),
    ).fetchall()


def _conversation_window(
    conn: sqlite3.Connection,
    chat_id: int,
    message_id: int,
    settings: Settings,
    as_of: str,
) -> list[dict]:
    rows = conn.execute(
        """SELECT message_id,date,text FROM messages WHERE chat_id=? AND message_id BETWEEN ? AND ?
           AND message_id!=? AND date<=? AND is_deleted=0 ORDER BY message_id""",
        (
            chat_id,
            message_id - settings.task_deep_dive_context_before,
            message_id + settings.task_deep_dive_context_after,
            message_id,
            as_of,
        ),
    ).fetchall()
    return [{"message_id": row[0], "date": row[1], "text": row[2]} for row in rows]


def _anchors(task: dict, context: BuiltContext) -> set[str]:
    values = [
        entity.get("canonical_name", "")
        for entity in (*context.people, *context.projects, *context.companies)
    ]
    values.append(task.get("title", ""))
    return {value.casefold() for value in values if len(value.strip()) >= 3}


def _related_chats(
    conn: sqlite3.Connection, task: dict, context: BuiltContext, as_of: str
) -> set[int]:
    chats = (
        {int(task["source_chat_id"])}
        if task.get("source_chat_id") is not None
        else set()
    )
    for collection in (context.relationships, context.events):
        for item in collection:
            if item.get("source_chat_id") is not None:
                chats.add(int(item["source_chat_id"]))
    project_id = task.get("related_project_id")
    if project_id is not None:
        chats.update(
            int(row[0])
            for row in conn.execute(
                """SELECT chat_id FROM conversation_segments
                   WHERE project_id=? AND started_at<=?
                     AND (ended_at IS NULL OR ended_at>?)""",
                (project_id, as_of, as_of),
            )
        )
    return chats


def _event_matches_task(event: dict, task: dict) -> bool:
    text = f"{event.get('title') or ''} {event.get('description') or ''}".casefold()
    return any(
        word in text for word in re.findall(r"[a-z0-9]{3,}", task["title"].casefold())
    )


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
