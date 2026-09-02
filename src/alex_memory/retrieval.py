"""Bounded SQL-first retrieval stages for Alex Memory intelligence."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import cast

from .config import Settings
from .context.graph import current_authoritative_edges
from .operational import normalize_alias
from .schema_support import fts5_available
from .utils import utc_now


@dataclass(slots=True)
class SearchResult:
    result_type: str
    title: str
    snippet: str
    date: str | None
    score: float
    chat_id: int | None = None
    message_id: int | None = None
    person_id: int | None = None
    company_id: int | None = None
    project_id: int | None = None
    task_id: int | None = None
    source_id: int | None = None

    @property
    def citation(self) -> str:
        if self.message_id is not None and self.chat_id is not None:
            return f"Telegram chat {self.chat_id} / msg {self.message_id}"
        if self.task_id is not None:
            return f"Task #{self.task_id}"
        return (
            f"{self.result_type.title()} #{self.source_id}"
            if self.source_id is not None
            else self.result_type.title()
        )


def retrieve(
    conn: sqlite3.Connection,
    question: str,
    settings: Settings,
    limit: int = 80,
    person_id: int | None = None,
) -> list[SearchResult]:
    """Collect bounded canonical, summary, message, and FTS evidence."""
    query = " ".join(question.split())
    if not query:
        return []
    lowered = normalize_alias(query)
    terms = [term for term in re.findall(r"[\w-]{3,}", lowered, flags=re.UNICODE)][:8]
    match_terms = terms[:4] or [lowered]
    entities = _entity_hints(conn, lowered)
    results: list[SearchResult] = []
    if person_id is not None:
        _append_person_contact_results(conn, person_id, results)
    _append_task_results(conn, settings, match_terms, lowered, entities, results)
    _append_entity_and_memory_results(conn, settings, match_terms, results)
    _append_summary_results(conn, settings, match_terms, results)
    _append_message_results(conn, settings, match_terms, lowered, entities, results)
    _append_fts_results(conn, settings, match_terms, lowered, entities, results)
    return _rank_results(results, limit)


def retrieve_related(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    settings: Settings,
    query: str | None = None,
    as_of: str | None = None,
) -> list[SearchResult]:
    """Return bounded records explicitly linked to one canonical entity.

    This deliberately does not delegate to lexical search: callers asking for
    related state must not receive an unrelated record that merely repeats the
    entity's name.  ``as_of`` is applied to temporal/canonical rows; current
    materializations are omitted because they cannot truthfully represent the
    past.
    """
    if entity_type not in {"person", "company", "project", "task"}:
        raise ValueError("unsupported related-entity type")
    _require_entity(conn, entity_type, entity_id)
    results: list[SearchResult] = []
    temporal = " AND updated_at<=?" if as_of else ""
    params: list[object] = [entity_id]
    if as_of:
        params.append(as_of)

    if entity_type == "task":
        task_rows = conn.execute(
            """SELECT task_id,title,COALESCE(details,''),status,updated_at,source_chat_id,
                      related_person_id,related_company_id,related_project_id
               FROM tasks WHERE task_id=?"""
            + temporal,
            params,
        ).fetchall()
    else:
        target_column = {
            "person": "related_person_id",
            "company": "related_company_id",
            "project": "related_project_id",
        }[entity_type]
        task_rows = conn.execute(
            """SELECT task_id,title,COALESCE(details,''),status,updated_at,source_chat_id,
                      related_person_id,related_company_id,related_project_id
               FROM tasks WHERE """
            + target_column
            + "=?"
            + temporal
            + " ORDER BY updated_at DESC LIMIT ?",
            [*params, settings.qa_max_tasks],
        ).fetchall()
    for (
        task_id,
        title,
        details,
        status,
        updated,
        chat,
        person,
        company,
        project,
    ) in task_rows:
        results.append(
            SearchResult(
                "task",
                str(title),
                f"{status.upper()} — {details}"[:500],
                updated,
                94,
                chat_id=chat,
                person_id=person,
                company_id=company,
                project_id=project,
                task_id=task_id,
                source_id=task_id,
            )
        )

    observation_column = "item_id" if entity_type == "task" else f"{entity_type}_id"
    observation_time = " AND source_date<=?" if as_of else ""
    observation_params: list[object] = [entity_id]
    if as_of:
        observation_params.append(as_of)
    for item_id, title, details, source_date, chat, message in conn.execute(
        """SELECT item_id,title,COALESCE(details,''),source_date,source_chat_id,source_message_id
           FROM ai_items WHERE """
        + observation_column
        + "=?"
        + observation_time
        + " ORDER BY source_date DESC,item_id DESC LIMIT ?",
        [*observation_params, settings.context_max_events],
    ):
        results.append(
            SearchResult(
                "observation",
                str(title),
                str(details)[:800],
                source_date,
                88,
                chat_id=chat,
                message_id=message,
                source_id=item_id,
            )
        )

    event_column = "task_id" if entity_type == "task" else f"{entity_type}_id"
    event_time = " AND COALESCE(occurred_at,observed_at,created_at)<=?" if as_of else ""
    event_params: list[object] = [entity_id]
    if as_of:
        event_params.append(as_of)
    for event_id, title, description, occurred_at, chat, message in conn.execute(
        """SELECT event_id,title,COALESCE(description,''),occurred_at,source_chat_id,source_message_id
           FROM context_events WHERE event_type != 'observation_recorded' AND """
        + event_column
        + "=?"
        + event_time
        + " ORDER BY COALESCE(occurred_at,created_at) DESC LIMIT ?",
        [*event_params, settings.context_max_events],
    ):
        results.append(
            SearchResult(
                "event",
                str(title),
                str(description)[:800],
                occurred_at,
                88,
                chat_id=chat,
                message_id=message,
                source_id=event_id,
            )
        )

    if entity_type != "task":
        fact_time = (
            " AND valid_from<=? AND (valid_to IS NULL OR valid_to>?)"
            if as_of
            else " AND is_current=1"
        )
        fact_params: list[object] = [entity_type, entity_id]
        if as_of:
            fact_params.extend([as_of, as_of])
        for fact_id, predicate, value, valid_from, chat, message in conn.execute(
            """SELECT fact_id,predicate,value_json,valid_from,source_chat_id,source_message_id
               FROM context_facts WHERE subject_type=? AND subject_id=?"""
            + fact_time
            + " ORDER BY valid_from DESC LIMIT ?",
            [*fact_params, settings.context_max_facts],
        ):
            results.append(
                SearchResult(
                    "fact",
                    str(predicate),
                    str(value)[:800],
                    valid_from,
                    86,
                    chat_id=chat,
                    message_id=message,
                    source_id=fact_id,
                )
            )

    if entity_type != "task":
        append_authoritative_graph_context(
            conn,
            entity_type,
            entity_id,
            as_of or utc_now(),
            settings.context_max_events,
            results,
        )

    return _rank_results(results, settings.qa_max_tasks + settings.context_max_events)


def _require_entity(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> None:
    table, key = {
        "person": ("people", "person_id"),
        "company": ("companies", "company_id"),
        "project": ("projects", "project_id"),
        "task": ("tasks", "task_id"),
    }[entity_type]
    if (
        conn.execute(f"SELECT 1 FROM {table} WHERE {key}=?", (entity_id,)).fetchone()
        is None
    ):
        raise ValueError(f"unknown {entity_type} {entity_id}")


def append_authoritative_graph_context(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    as_of: str,
    limit: int,
    results: list[SearchResult],
) -> None:
    """Append one-hop authoritative graph context with exact provenance.

    This is deliberately an entity-scoped presentation of the existing graph
    contract, not a compatibility-reader cutover or a graph ranking pass.
    """
    for edge in current_authoritative_edges(
        conn, [(entity_type, entity_id)], as_of, limit=min(limit, 40)
    ):
        from_type, from_id = str(edge["from_type"]), cast(int, edge["from_id"])
        to_type, to_id = str(edge["to_type"]), cast(int, edge["to_id"])
        if (from_type, from_id) == (entity_type, entity_id):
            other_type, other_id = to_type, to_id
        elif (to_type, to_id) == (entity_type, entity_id):
            other_type, other_id = from_type, from_id
        else:
            continue
        other_name = _canonical_entity_name(conn, other_type, other_id)
        if other_name is None:
            continue
        chat_id, message_id = _edge_evidence_locator(conn, edge)
        authority = str(edge["authority_status"])
        if authority != "manual" and (chat_id is None or message_id is None):
            continue
        results.append(
            SearchResult(
                "connection",
                f"{other_type.title()}: {other_name}",
                f"{authority.upper()} — {edge['relationship_type']}",
                str(edge["valid_from"]),
                87 if authority == "accepted" else 85,
                chat_id=chat_id,
                message_id=message_id,
                **{f"{other_type}_id": other_id},
                source_id=(
                    cast(int, edge["edge_id"]) if edge["edge_id"] is not None else None
                ),
            )
        )


def _canonical_entity_name(
    conn: sqlite3.Connection, entity_type: str, entity_id: int
) -> str | None:
    table, column, name_column = {
        "person": ("people", "person_id", "canonical_name"),
        "company": ("companies", "company_id", "canonical_name"),
        "project": ("projects", "project_id", "canonical_name"),
        "task": ("tasks", "task_id", "title"),
    }.get(entity_type, ("", "", ""))
    if not table:
        return None
    row = conn.execute(
        f"SELECT {name_column} FROM {table} WHERE {column}=?", (entity_id,)
    ).fetchone()
    return str(row[0]) if row is not None else None


def _edge_evidence_locator(
    conn: sqlite3.Connection, edge: dict[str, object]
) -> tuple[int | None, int | None]:
    source_evidence = edge.get("source_evidence")
    if isinstance(source_evidence, tuple) and len(source_evidence) == 2:
        return cast(int, source_evidence[0]), cast(int, source_evidence[1])
    claim_ids = edge.get("claim_ids")
    if not isinstance(claim_ids, tuple) or not claim_ids:
        return None, None
    marks = ",".join("?" for _ in claim_ids)
    row = conn.execute(
        f"""SELECT chat_id,message_id FROM semantic_claim_evidence
               WHERE claim_id IN ({marks})
               ORDER BY claim_id,ordinal LIMIT 1""",
        list(claim_ids),
    ).fetchone()
    return (int(row[0]), int(row[1])) if row is not None else (None, None)


def _append_person_contact_results(
    conn: sqlite3.Connection, person_id: int, results: list[SearchResult]
) -> None:
    row = conn.execute(
        """SELECT current_summary,long_term_summary,last_contact_at FROM person_context_state
           WHERE person_id=?""",
        (person_id,),
    ).fetchone()
    if row:
        results.append(
            SearchResult(
                "conversation",
                "Current contact context",
                str(row[0] or ""),
                row[2],
                98,
                person_id=person_id,
                source_id=person_id,
            )
        )
        if row[1]:
            results.append(
                SearchResult(
                    "relationship",
                    "Relationship history",
                    str(row[1]),
                    row[2],
                    72,
                    person_id=person_id,
                    source_id=person_id,
                )
            )
    for task_id, title, details, status, updated, chat, project in conn.execute(
        """SELECT task_id,title,details,status,updated_at,source_chat_id,related_project_id
           FROM tasks WHERE related_person_id=? ORDER BY updated_at DESC LIMIT 20""",
        (person_id,),
    ):
        results.append(
            SearchResult(
                "task",
                title,
                f"{status.upper()} — {details or ''}"[:500],
                updated,
                94,
                chat_id=chat,
                person_id=person_id,
                project_id=project,
                task_id=task_id,
                source_id=task_id,
            )
        )


def _append_task_results(
    conn: sqlite3.Connection,
    settings: Settings,
    terms: list[str],
    lowered: str,
    entities: tuple[list[int], list[int], list[int]],
    results: list[SearchResult],
) -> None:
    people, companies, projects = entities
    waiting = any(word in lowered for word in ("waiting", "wait", "жду", "ожида"))
    attention = "attention" in lowered or "needs my" in lowered or "overdue" in lowered
    title_match, title_params = _all_terms_like("title", terms)
    details_match, details_params = _all_terms_like("COALESCE(details,'')", terms)
    rows = conn.execute(
        """SELECT task_id,title,COALESCE(details,''),status,due_date,updated_at,source_chat_id,related_person_id,related_company_id,related_project_id
           FROM tasks WHERE (%s OR %s OR related_person_id IN (%s) OR related_company_id IN (%s) OR related_project_id IN (%s))
           ORDER BY CASE WHEN status='waiting' THEN 0 WHEN status='open' THEN 1 ELSE 2 END, due_date, updated_at DESC LIMIT ?"""
        % (
            title_match,
            details_match,
            _placeholders(people),
            _placeholders(companies),
            _placeholders(projects),
        ),
        [
            *title_params,
            *details_params,
            *people,
            *companies,
            *projects,
            settings.qa_max_tasks,
        ],
    ).fetchall()
    for (
        task_id,
        title,
        details,
        status,
        due,
        updated,
        chat,
        person,
        company,
        project,
    ) in rows:
        score = (
            80
            + (30 if waiting and status == "waiting" else 0)
            + (20 if attention and status in {"open", "waiting"} else 0)
            + (10 if due and due < date.today().isoformat() else 0)
        )
        results.append(
            SearchResult(
                "task",
                title,
                f"{status.upper()} — {details}"[:500],
                updated or due,
                score,
                chat_id=chat,
                person_id=person,
                company_id=company,
                project_id=project,
                task_id=task_id,
                source_id=task_id,
            )
        )


def _append_entity_and_memory_results(
    conn: sqlite3.Connection,
    settings: Settings,
    terms: list[str],
    results: list[SearchResult],
) -> None:
    name_match, name_params = _all_terms_like("canonical_name", terms)
    for table, kind, id_col in (
        ("people", "person", "person_id"),
        ("companies", "company", "company_id"),
        ("projects", "project", "project_id"),
    ):
        for entity_id, name, updated in conn.execute(
            f"SELECT {id_col}, canonical_name, updated_at FROM {table} WHERE {name_match} ORDER BY updated_at DESC LIMIT 10",
            name_params,
        ):
            results.append(
                SearchResult(
                    kind,
                    name,
                    f"Canonical {kind}",
                    updated,
                    70,
                    source_id=int(entity_id),
                    **{f"{kind}_id": int(entity_id)},
                )
            )
    key_match, key_params = _all_terms_like("title", terms)
    summary_match, summary_params = _all_terms_like("details", terms)
    rows = conn.execute(
        """SELECT person_id,company_id,project_id,title,details,source_date,item_id
           FROM ai_items WHERE (%s OR %s) ORDER BY source_date DESC,item_id DESC LIMIT ?"""
        % (key_match, summary_match),
        [*key_params, *summary_params, settings.qa_max_memories],
    ).fetchall()
    for person_id, company_id, project_id, key, summary, updated, item_id in rows:
        entity = {
            name: int(value)
            for name, value in (
                ("person_id", person_id),
                ("company_id", company_id),
                ("project_id", project_id),
            )
            if value is not None
        }
        results.append(
            SearchResult(
                "observation",
                key,
                summary[:800],
                updated,
                60,
                source_id=item_id,
                **entity,
            )
        )


def _append_summary_results(
    conn: sqlite3.Connection,
    settings: Settings,
    terms: list[str],
    results: list[SearchResult],
) -> None:
    summary_match, summary_params = _all_terms_like("summary", terms)
    for table, label, date_col in (
        ("memory_chunks", "summary", "date_to"),
        ("chat_daily_summaries", "daily summary", "summary_date"),
        ("chat_monthly_summaries", "monthly summary", "summary_month"),
    ):
        if table == "memory_chunks":
            rows = conn.execute(
                f"SELECT chunk_id,chat_id,summary,date_to FROM memory_chunks WHERE {summary_match} ORDER BY date_to DESC LIMIT ?",
                [*summary_params, settings.qa_max_summaries],
            ).fetchall()
            for source_id, chat_id, summary, value_date in rows:
                results.append(
                    SearchResult(
                        "summary",
                        label,
                        summary[:1000],
                        value_date,
                        50,
                        chat_id=chat_id,
                        source_id=source_id,
                    )
                )
        else:
            rows = conn.execute(
                f"SELECT chat_id,summary,{date_col} FROM {table} WHERE {summary_match} ORDER BY {date_col} DESC LIMIT ?",
                [*summary_params, settings.qa_max_summaries],
            ).fetchall()
            for chat_id, summary, value_date in rows:
                results.append(
                    SearchResult(
                        "summary",
                        label,
                        summary[:1000],
                        value_date,
                        45,
                        chat_id=chat_id,
                    )
                )
    brief_match, brief_params = _all_terms_like("data_json", terms)
    for brief_date, data_json in conn.execute(
        f"SELECT brief_date,data_json FROM daily_briefs WHERE {brief_match} ORDER BY brief_date DESC LIMIT ?",
        [*brief_params, settings.qa_max_summaries],
    ):
        results.append(
            SearchResult(
                "brief", f"Daily Brief {brief_date}", data_json[:1000], brief_date, 42
            )
        )


def _append_message_results(
    conn: sqlite3.Connection,
    settings: Settings,
    terms: list[str],
    lowered: str,
    entities: tuple[list[int], list[int], list[int]],
    results: list[SearchResult],
) -> None:
    _, _, projects = entities
    text_match, text_params = _all_terms_like("m.text", terms)
    rows = conn.execute(
        """SELECT m.chat_id,m.message_id,COALESCE(c.title,CAST(m.chat_id AS TEXT)),m.text,m.date,
                  COALESCE(mc.importance,'normal'),COALESCE(mc.content_type,'information'),
                  EXISTS(
                      SELECT 1 FROM conversation_segments AS s
                      WHERE s.chat_id=m.chat_id AND s.project_id IN (%s)
                        AND s.started_at<=m.date AND (s.ended_at IS NULL OR s.ended_at>m.date)
                  )
           FROM messages m LEFT JOIN chats c ON c.chat_id=m.chat_id
           LEFT JOIN message_classifications mc ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
           WHERE COALESCE(m.is_deleted,0)=0 AND %s
           ORDER BY CASE COALESCE(mc.importance,'normal') WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END,
                    m.date DESC LIMIT ?"""
        % (_placeholders(projects), text_match),
        [*projects, *text_params, settings.qa_max_raw_messages],
    ).fetchall()
    for (
        chat_id,
        message_id,
        title,
        text,
        value_date,
        importance,
        content_type,
        segment_match,
    ) in rows:
        score = 35 + (15 if any(entities) else 0) + _importance_score(importance)
        if segment_match:
            score += 18
        if (
            any(word in lowered for word in ("decision", "decided"))
            and content_type == "decision"
        ):
            score += 20
        results.append(
            SearchResult(
                "message",
                str(title),
                str(text)[:1000],
                value_date,
                score,
                chat_id=chat_id,
                message_id=message_id,
                source_id=message_id,
            )
        )


def _append_fts_results(
    conn: sqlite3.Connection,
    settings: Settings,
    terms: list[str],
    lowered: str,
    entities: tuple[list[int], list[int], list[int]],
    results: list[SearchResult],
) -> None:
    if not fts5_available(conn):
        return
    query = (
        " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        or f'"{lowered}"'
    )
    _, _, projects = entities
    rows = conn.execute(
        """SELECT m.chat_id,m.message_id,COALESCE(c.title,CAST(m.chat_id AS TEXT)),m.text,m.date,
                      COALESCE(mc.importance,'normal'),
                      EXISTS(
                          SELECT 1 FROM conversation_segments AS s
                          WHERE s.chat_id=m.chat_id AND s.project_id IN (%s)
                            AND s.started_at<=m.date AND (s.ended_at IS NULL OR s.ended_at>m.date)
                      )
               FROM messages_fts f JOIN messages m ON m.chat_id=f.chat_id AND m.message_id=f.message_id
               LEFT JOIN chats c ON c.chat_id=m.chat_id
               LEFT JOIN message_classifications mc ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
               WHERE messages_fts MATCH ? AND COALESCE(m.is_deleted,0)=0
               ORDER BY CASE COALESCE(mc.importance,'normal') WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, m.date DESC LIMIT ?"""
        % _placeholders(projects),
        [*projects, query, settings.qa_max_raw_messages],
    ).fetchall()
    for (
        chat_id,
        message_id,
        title,
        text,
        value_date,
        importance,
        segment_match,
    ) in rows:
        results.append(
            SearchResult(
                "message",
                str(title),
                str(text)[:1000],
                value_date,
                55 + _importance_score(importance) + (18 if segment_match else 0),
                chat_id=chat_id,
                message_id=message_id,
                source_id=message_id,
            )
        )
    rows = conn.execute(
        """SELECT t.task_id,t.title,COALESCE(t.details,''),t.status,t.due_date,t.updated_at,t.source_chat_id,t.related_person_id,t.related_company_id,t.related_project_id
               FROM tasks_fts f JOIN tasks t ON t.task_id=f.task_id WHERE tasks_fts MATCH ? LIMIT ?""",
        (query, settings.qa_max_tasks),
    ).fetchall()
    for (
        task_id,
        title,
        details,
        status,
        due,
        updated,
        chat,
        person,
        company,
        project,
    ) in rows:
        results.append(
            SearchResult(
                "task",
                title,
                f"{status.upper()} — {details}"[:500],
                updated or due,
                85,
                chat_id=chat,
                person_id=person,
                company_id=company,
                project_id=project,
                task_id=task_id,
                source_id=task_id,
            )
        )


def _rank_results(results: list[SearchResult], limit: int) -> list[SearchResult]:
    seen: set[tuple[str, int | None, int | None, int | None, str | None]] = set()
    unique: list[SearchResult] = []
    for result in sorted(
        results, key=lambda item: (item.score, item.date or ""), reverse=True
    ):
        key = (
            result.result_type,
            result.source_id,
            result.message_id,
            result.chat_id,
            result.date
            if result.source_id is None and result.message_id is None
            else None,
        )
        if key not in seen:
            seen.add(key)
            unique.append(result)
    return unique[:limit]


def _importance_score(importance: str) -> int:
    return {"critical": 30, "high": 20, "normal": 8, "low": 0, "noise": -30}.get(
        importance, 0
    )


def _entity_hints(
    conn: sqlite3.Connection, query: str
) -> tuple[list[int], list[int], list[int]]:
    found: dict[str, list[int]] = {"person": [], "company": [], "project": []}
    for entity_type, entity_id, _alias in conn.execute(
        """SELECT entity_type,entity_id,normalized_alias FROM entity_aliases
           WHERE length(normalized_alias) >= 3 AND instr(?, normalized_alias) > 0
           ORDER BY length(normalized_alias) DESC LIMIT 48""",
        (query,),
    ):
        found[entity_type].append(int(entity_id))
    return (
        sorted(set(found["person"])) or [-1],
        sorted(set(found["company"])) or [-1],
        sorted(set(found["project"])) or [-1],
    )


def _placeholders(values: list[int]) -> str:
    return ",".join("?" for _ in values)


def _all_terms_like(column: str, terms: list[str]) -> tuple[str, list[str]]:
    """Build a bounded, order-independent SQL LIKE match for one text column."""
    return (
        " AND ".join(f"{column} LIKE ?" for _ in terms),
        [f"%{term}%" for term in terms],
    )
