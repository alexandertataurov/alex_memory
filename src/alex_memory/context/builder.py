from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime

from ..config import Settings
from .models import BuiltContext, ContextRequest
from .ranking import highest, rank_item
from .repository import current_facts


_ENTITY_TABLES = {
    "person": ("people", "person_id"),
    "company": ("companies", "company_id"),
    "project": ("projects", "project_id"),
}


class ContextBuilder:
    """Build bounded context from canonical state, not a database-sized message scan."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn, self.settings = conn, settings

    def build(self, request: ContextRequest) -> BuiltContext:
        historical = request.as_of is not None
        as_of = (
            request.as_of.isoformat()
            if request.as_of
            else datetime.now().astimezone().isoformat()
        )
        seed_distances = self._resolve_entities(request, as_of)
        relationships, distances = self._expand_relationships(seed_distances, as_of)
        people = self._entities(
            "person", distances, as_of, self.settings.context_max_people, historical
        )
        companies = self._entities(
            "company", distances, as_of, self.settings.context_max_companies, historical
        )
        projects = self._entities(
            "project", distances, as_of, self.settings.context_max_projects, historical
        )
        tasks = self._tasks(distances, request, as_of, historical)
        events = self._events(distances, request, as_of)
        facts, historical_facts = self._facts(people, companies, projects, as_of)
        conflicts = self._conflicts(distances, as_of)
        summaries = self._summaries(distances, as_of, historical)
        segments = self._segments(request, distances, as_of)
        evidence = self._evidence(request, tasks, events, facts, relationships, as_of)

        diagnostics: dict[str, object] = {
            "purpose": request.purpose,
            "resolved_people": len(people),
            "resolved_projects": len(projects),
            "resolved_companies": len(companies),
            "graph_expansion": len(relationships),
            "current_facts": len(facts),
            "historical_facts": len(historical_facts),
            "conflicts": len(conflicts),
            "open_tasks": len(tasks),
            "events": len(events),
            "summaries": len(summaries),
            "conversation_segments": len(segments),
            "raw_messages": len(evidence),
            "ambiguous_entities": 0,
        }
        if historical:
            diagnostics["historical_fidelity"] = (
                "partial: mutable entity, task, global lifecycle, and current summary state omitted"
            )
        diagnostics["context_score"] = round(
            sum(
                float(item.get("score", 0))
                for collection in (
                    facts,
                    tasks,
                    relationships,
                    events,
                    conflicts,
                    summaries,
                    evidence,
                )
                for item in collection
            ),
            2,
        )
        return BuiltContext(
            request.purpose,
            as_of,
            self._global_state(as_of, historical),
            people,
            projects,
            companies,
            relationships,
            tasks,
            events,
            facts,
            historical_facts,
            conflicts,
            summaries,
            evidence,
            segments,
            diagnostics,
        )

    def _resolve_entities(
        self, request: ContextRequest, as_of: str
    ) -> dict[tuple[str, int], int]:
        distances: dict[tuple[str, int], int] = {}
        for kind, ids in (
            ("person", request.person_ids),
            ("company", request.company_ids),
            ("project", request.project_ids),
        ):
            for entity_id in ids:
                distances[(kind, entity_id)] = 0
        query = request.query.casefold()
        if query:
            terms = _alias_candidates(query)
            if terms:
                rows = self.conn.execute(
                    f"SELECT entity_type,entity_id FROM entity_aliases WHERE normalized_alias IN ({','.join('?' for _ in terms)})",
                    sorted(terms),
                ).fetchall()
                for kind, entity_id in rows:
                    distances[(str(kind), int(entity_id))] = 0
        if request.chat_id is not None:
            rows = self.conn.execute(
                """SELECT related_person_id,related_company_id,related_project_id
                   FROM tasks WHERE source_chat_id=? AND updated_at<=? AND status IN ('open','waiting')
                   UNION ALL
                   SELECT person_id,company_id,project_id FROM ai_items
                   WHERE source_chat_id=? AND source_date<=?""",
                (request.chat_id, as_of, request.chat_id, as_of),
            ).fetchall()
            for person_id, company_id, project_id in rows:
                for kind, entity_id in (
                    ("person", person_id),
                    ("company", company_id),
                    ("project", project_id),
                ):
                    if entity_id is not None:
                        distances[(kind, int(entity_id))] = 0
        for task_id in request.task_ids:
            if request.as_of is not None:
                continue
            row = self.conn.execute(
                "SELECT related_person_id,related_company_id,related_project_id FROM tasks WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row:
                for kind, entity_id in zip(
                    ("person", "company", "project"), row, strict=True
                ):
                    if entity_id is not None:
                        distances[(kind, int(entity_id))] = 0
        return distances

    def _expand_relationships(
        self, seeds: dict[tuple[str, int], int], as_of: str
    ) -> tuple[list[dict], dict[tuple[str, int], int]]:
        distances = dict(seeds)
        frontier = list(seeds)
        collected: list[dict] = []
        for depth in range(self.settings.context_max_graph_depth + 1):
            if not frontier:
                break
            clauses = " OR ".join(
                "(from_type=? AND from_id=?) OR (to_type=? AND to_id=?)"
                for _ in frontier
            )
            params: list[object] = []
            for kind, entity_id in frontier:
                params.extend((kind, entity_id, kind, entity_id))
            rows = self.conn.execute(
                f"""SELECT relationship_id,from_type,from_id,to_type,to_id,relationship_type,
                           valid_from,valid_to,is_current,confidence,source_chat_id,source_message_id,source_claim_id,updated_at
                    FROM relationships WHERE ({clauses}) AND valid_from<=?
                    AND (valid_to IS NULL OR valid_to>?) LIMIT 160""",
                [*params, as_of, as_of],
            ).fetchall()
            next_frontier: list[tuple[str, int]] = []
            for row in rows:
                relation = {
                    "relationship_id": row[0],
                    "from_type": row[1],
                    "from_id": row[2],
                    "to_type": row[3],
                    "to_id": row[4],
                    "relationship_type": row[5],
                    "description": f"{row[1]} {row[2]} → {row[5]} → {row[3]} {row[4]}",
                    "valid_from": row[6],
                    "valid_to": row[7],
                    "is_current": bool(row[8]),
                    "confidence": row[9],
                    "source_chat_id": row[10],
                    "source_message_id": row[11],
                    "source_claim_id": row[12],
                    "updated_at": row[13],
                }
                relation = rank_item(
                    relation, "relationship", graph_distance=depth, now=as_of
                )
                if relation["relationship_id"] not in {
                    item["relationship_id"] for item in collected
                }:
                    collected.append(relation)
                for kind, entity_id in (
                    (str(row[1]), int(row[2])),
                    (str(row[3]), int(row[4])),
                ):
                    if kind not in _ENTITY_TABLES:
                        continue
                    if (
                        (kind, entity_id) not in distances
                        and depth < self.settings.context_max_graph_depth
                    ):
                        distances[(kind, entity_id)] = depth + 1
                        next_frontier.append((kind, entity_id))
            frontier = next_frontier
        return highest(collected, 80), distances

    def _entities(
        self,
        kind: str,
        distances: dict[tuple[str, int], int],
        as_of: str,
        limit: int,
        historical: bool,
    ) -> list[dict]:
        table, key = _ENTITY_TABLES[kind]
        records: list[dict] = []
        for (entity_kind, entity_id), distance in distances.items():
            if entity_kind != kind:
                continue
            row = self.conn.execute(
                f"SELECT * FROM {table} WHERE {key}=?", (entity_id,)
            ).fetchone()
            if not row:
                continue
            columns = [
                column[0]
                for column in self.conn.execute(
                    f"SELECT * FROM {table} WHERE {key}=?", (entity_id,)
                ).description
            ]
            record = dict(zip(columns, row, strict=True))
            if historical:
                record = {
                    "id": entity_id,
                    "type": kind,
                    "canonical_name": record["canonical_name"],
                    "historical_fidelity": "identity only; mutable entity state unavailable",
                    "pinned": [],
                }
            else:
                record.update(
                    {
                        "id": entity_id,
                        "type": kind,
                        "pinned": [
                            item[0]
                            for item in self.conn.execute(
                                "SELECT content FROM pinned_memory WHERE entity_type=? AND entity_id=? ORDER BY updated_at DESC LIMIT 8",
                                (kind, entity_id),
                            )
                        ],
                    }
                )
            record = rank_item(
                record,
                "pinned" if record["pinned"] else "relationship",
                direct_match=distance == 0,
                graph_distance=distance,
                now=as_of,
            )
            records.append(record)
        return highest(records, limit)

    def _tasks(
        self,
        distances: dict[tuple[str, int], int],
        request: ContextRequest,
        as_of: str,
        historical: bool,
    ) -> list[dict]:
        if historical:
            return []
        predicates = ["status IN ('open','waiting')", "updated_at<=?"]
        params: list[object] = [as_of]
        ids_by_type = {
            kind: [
                entity_id
                for (entity_kind, entity_id), _ in distances.items()
                if entity_kind == kind
            ]
            for kind in _ENTITY_TABLES
        }
        links = []
        for column, kind in (
            ("related_person_id", "person"),
            ("related_company_id", "company"),
            ("related_project_id", "project"),
        ):
            if ids_by_type[kind]:
                links.append(
                    f"{column} IN ({','.join('?' for _ in ids_by_type[kind])})"
                )
                params.extend(ids_by_type[kind])
        if request.task_ids:
            links.append(f"task_id IN ({','.join('?' for _ in request.task_ids)})")
            params.extend(request.task_ids)
        if request.chat_id is not None:
            links.append("source_chat_id=?")
            params.append(request.chat_id)
        if not links and request.purpose not in {"daily_brief", "global_state"}:
            return []
        if links:
            predicates.append("(" + " OR ".join(links) + ")")
        rows = self.conn.execute(
            f"""SELECT task_id,title,details,status,owner,due_date,confidence,related_person_id,
                       related_company_id,related_project_id,source_chat_id,source_claim_id,updated_at
                FROM tasks WHERE {" AND ".join(predicates)}
                ORDER BY updated_at DESC LIMIT ?""",
            [*params, self.settings.context_max_tasks * 3],
        ).fetchall()
        result = []
        for row in rows:
            direct = request.chat_id == row[10] or any(
                (kind, row[index]) in distances and distances[(kind, row[index])] == 0
                for kind, index in (("person", 7), ("company", 8), ("project", 9))
                if row[index] is not None
            )
            item = {
                "task_id": row[0],
                "title": row[1],
                "details": row[2],
                "status": row[3],
                "owner": row[4],
                "due_date": row[5],
                "confidence": row[6],
                "person_id": row[7],
                "company_id": row[8],
                "project_id": row[9],
                "source_chat_id": row[10],
                "source_claim_id": row[11],
                "updated_at": row[12],
            }
            result.append(rank_item(item, "task", direct_match=direct, now=as_of))
        return highest(result, self.settings.context_max_tasks)

    def _events(
        self, distances: dict[tuple[str, int], int], request: ContextRequest, as_of: str
    ) -> list[dict]:
        predicates = ["COALESCE(occurred_at,observed_at)<=?"]
        params: list[object] = [as_of]
        links = []
        for column, kind in (
            ("person_id", "person"),
            ("company_id", "company"),
            ("project_id", "project"),
        ):
            ids = [
                entity_id
                for (entity_kind, entity_id), _ in distances.items()
                if entity_kind == kind
            ]
            if ids:
                links.append(f"{column} IN ({','.join('?' for _ in ids)})")
                params.extend(ids)
        if request.chat_id is not None:
            links.append("source_chat_id=?")
            params.append(request.chat_id)
        if not links and request.purpose not in {"daily_brief", "global_state"}:
            return []
        if links:
            predicates.append("(" + " OR ".join(links) + ")")
        rows = self.conn.execute(
            f"""SELECT event_id,event_type,title,description,occurred_at,person_id,company_id,
                       project_id,task_id,source_chat_id,source_message_id,source_claim_id,confidence,created_at
                FROM context_events WHERE event_type != 'observation_recorded'
                  AND {" AND ".join(predicates)}
                ORDER BY COALESCE(occurred_at,created_at) DESC LIMIT ?""",
            [*params, self.settings.context_max_events * 3],
        ).fetchall()
        result = []
        for row in rows:
            direct = request.chat_id == row[9] or any(
                (kind, row[index]) in distances and distances[(kind, row[index])] == 0
                for kind, index in (("person", 5), ("company", 6), ("project", 7))
                if row[index] is not None
            )
            item = {
                "event_id": row[0],
                "event_type": row[1],
                "title": row[2],
                "description": row[3],
                "occurred_at": row[4],
                "person_id": row[5],
                "company_id": row[6],
                "project_id": row[7],
                "task_id": row[8],
                "source_chat_id": row[9],
                "source_message_id": row[10],
                "source_claim_id": row[11],
                "confidence": row[12],
                "updated_at": row[13],
            }
            result.append(rank_item(item, "event", direct_match=direct, now=as_of))
        return highest(result, self.settings.context_max_events)

    def _facts(
        self,
        people: list[dict],
        companies: list[dict],
        projects: list[dict],
        as_of: str,
    ) -> tuple[list[dict], list[dict]]:
        current: list[dict] = []
        history: list[dict] = []
        for entity in [*people, *companies, *projects]:
            kind, entity_id = str(entity["type"]), int(entity["id"])
            for item in current_facts(
                self.conn, kind, entity_id, as_of, self.settings.context_max_facts
            ):
                item.update(
                    {"subject_type": kind, "subject_id": entity_id, "is_current": True}
                )
                current.append(
                    rank_item(
                        item,
                        "fact",
                        direct_match=float(entity["score"]) >= 75,
                        now=as_of,
                    )
                )
            rows = self.conn.execute(
                """SELECT predicate,value_json,valid_from,valid_to,confidence,source_chat_id,source_message_id,source_claim_id
                   FROM context_facts WHERE subject_type=? AND subject_id=? AND valid_to IS NOT NULL
                   AND valid_from<=? ORDER BY valid_to DESC LIMIT 8""",
                (kind, entity_id, as_of),
            ).fetchall()
            for row in rows:
                history.append(
                    {
                        "predicate": row[0],
                        "value": json.loads(row[1]),
                        "valid_from": row[2],
                        "valid_to": row[3],
                        "confidence": row[4],
                        "source_chat_id": row[5],
                        "source_message_id": row[6],
                        "source_claim_id": row[7],
                        "subject_type": kind,
                        "subject_id": entity_id,
                    }
                )
        return highest(current, self.settings.context_max_facts), history[
            : self.settings.context_max_facts
        ]

    def _summaries(
        self,
        distances: dict[tuple[str, int], int],
        as_of: str,
        historical: bool,
    ) -> list[dict]:
        result: list[dict] = []
        for (kind, entity_id), distance in distances.items():
            column = {
                "person": "person_id",
                "company": "company_id",
                "project": "project_id",
            }[kind]
            rows = self.conn.execute(
                f"""SELECT title,details,item_id,confidence,source_date FROM ai_items
                    WHERE {column}=? AND source_date<=?
                    ORDER BY source_date DESC,item_id DESC LIMIT 8""",
                (entity_id, as_of),
            ).fetchall()
            for row in rows:
                item = {
                    "entity_type": kind,
                    "entity_id": entity_id,
                    "memory_key": row[0],
                    "summary": f"{row[0]}: {row[1]}"[:2000],
                    "source_ai_item_id": row[2],
                    "confidence": row[3],
                    "updated_at": row[4],
                }
                result.append(
                    rank_item(
                        item,
                        "summary",
                        direct_match=distance == 0,
                        graph_distance=distance,
                        now=as_of,
                    )
                )
            if kind == "person" and not historical:
                contact = self.conn.execute(
                    """SELECT current_summary,long_term_summary,updated_at FROM person_context_state
                       WHERE person_id=? AND updated_at<=?""",
                    (entity_id, as_of),
                ).fetchone()
                if contact:
                    for key, summary in (
                        ("current_conversation_context", contact[0]),
                        ("long_term_relationship_context", contact[1]),
                    ):
                        if summary:
                            result.append(
                                rank_item(
                                    {
                                        "entity_type": kind,
                                        "entity_id": entity_id,
                                        "memory_key": key,
                                        "summary": summary,
                                        "confidence": 0.8,
                                        "updated_at": contact[2],
                                    },
                                    "summary",
                                    direct_match=distance == 0,
                                    graph_distance=distance,
                                    now=as_of,
                                )
                            )
        return highest(result, self.settings.context_max_summaries)

    def _segments(
        self,
        request: ContextRequest,
        distances: dict[tuple[str, int], int],
        as_of: str,
    ) -> list[dict]:
        project_ids = [
            entity_id for (kind, entity_id), _ in distances.items() if kind == "project"
        ]
        predicates = ["s.started_at<=?", "(s.ended_at IS NULL OR s.ended_at>?)"]
        parameters: list[object] = [as_of, as_of]
        links: list[str] = []
        if request.chat_id is not None:
            links.append("s.chat_id=?")
            parameters.append(request.chat_id)
        if project_ids:
            links.append(f"s.project_id IN ({','.join('?' for _ in project_ids)})")
            parameters.extend(project_ids)
        rows: list[tuple] = []
        if links:
            predicates.append("(" + " OR ".join(links) + ")")
            rows = self.conn.execute(
                f"""SELECT s.segment_id,s.chat_id,s.project_id,p.canonical_name,s.started_at,
                           s.ended_at,s.anchor_count,s.confidence
                    FROM conversation_segments AS s JOIN projects AS p ON p.project_id=s.project_id
                    WHERE {" AND ".join(predicates)}
                    ORDER BY s.started_at DESC LIMIT 12""",
                parameters,
            ).fetchall()
        result = [
            {
                "segment_id": row[0],
                "source_chat_id": row[1],
                "project_id": row[2],
                "project_name": row[3],
                "started_at": row[4],
                "ended_at": row[5],
                "confidence": row[7],
                "description": f"chat {row[1]} from {row[4]} to {row[5] or 'present'} ({row[6]} anchors)",
            }
            for row in rows
        ]
        person_ids = [
            entity_id for (kind, entity_id), _ in distances.items() if kind == "person"
        ]
        if person_ids:
            placeholders = ",".join("?" for _ in person_ids)
            contact_rows = self.conn.execute(
                f"""SELECT s.segment_id,s.person_id,s.conversation_id,s.primary_project_id,
                           p.canonical_name,s.started_at,s.ended_at,s.summary,s.confidence
                    FROM conversation_contact_segments AS s
                    LEFT JOIN projects AS p ON p.project_id=s.primary_project_id
                    WHERE s.person_id IN ({placeholders}) AND s.started_at<=?
                      AND (s.ended_at IS NULL OR s.ended_at>?)
                    ORDER BY s.started_at DESC LIMIT 12""",
                [*person_ids, as_of, as_of],
            ).fetchall()
            result.extend(
                {
                    "segment_id": row[0],
                    "person_id": row[1],
                    "source_chat_id": int(row[2]) if str(row[2]).isdigit() else None,
                    "project_id": row[3],
                    "project_name": row[4] or "General conversation",
                    "started_at": row[5],
                    "ended_at": row[6],
                    "confidence": row[8],
                    "description": row[7] or "Accepted contact activity",
                }
                for row in contact_rows
            )
        return result[:12]

    def _conflicts(
        self, distances: dict[tuple[str, int], int], as_of: str
    ) -> list[dict]:
        result: list[dict] = []
        for (kind, entity_id), distance in distances.items():
            rows = self.conn.execute(
                """SELECT conflict_id,predicate,existing_fact_id,new_observation_id,conflict_type,
                           created_at FROM context_conflicts
                   WHERE subject_type=? AND subject_id=? AND status='pending' AND created_at<=?
                   ORDER BY created_at DESC LIMIT 8""",
                (kind, entity_id, as_of),
            ).fetchall()
            for row in rows:
                item = {
                    "conflict_id": row[0],
                    "predicate": row[1],
                    "description": f"{row[4]} between existing fact {row[2]} and observation {row[3]}",
                    "updated_at": row[5],
                    "subject_type": kind,
                    "subject_id": entity_id,
                }
                result.append(
                    rank_item(
                        item,
                        "event",
                        direct_match=distance == 0,
                        graph_distance=distance,
                        now=as_of,
                    )
                )
        return highest(result, self.settings.context_max_facts)

    def _evidence(
        self,
        request: ContextRequest,
        tasks: list[dict],
        events: list[dict],
        facts: list[dict],
        relationships: list[dict],
        as_of: str,
    ) -> list[dict]:
        if not request.include_raw_evidence:
            return []
        message_pairs: set[tuple[int, int]] = set()
        for collection in (tasks, events, facts, relationships):
            for item in collection:
                source_chat_id = item.get("source_chat_id")
                source_message_id = item.get("source_message_id")
                if isinstance(source_chat_id, int) and isinstance(
                    source_message_id, int
                ):
                    message_pairs.add((source_chat_id, source_message_id))
        claim_ids = {
            int(item["source_claim_id"])
            for collection in (tasks, events, facts, relationships)
            for item in collection
            if isinstance(item.get("source_claim_id"), int)
        }
        if claim_ids:
            placeholders = ",".join("?" for _ in claim_ids)
            message_pairs.update(
                (int(chat_id), int(message_id))
                for chat_id, message_id in self.conn.execute(
                    f"""SELECT source_chat_id,source_message_id
                        FROM semantic_claim_evidence WHERE claim_id IN ({placeholders})""",
                    sorted(claim_ids),
                )
            )
        if not message_pairs:
            return []
        predicates = " OR ".join("(chat_id=? AND message_id=?)" for _ in message_pairs)
        parameters: list[object] = [
            value for pair in sorted(message_pairs) for value in pair
        ]
        rows = self.conn.execute(
            f"""SELECT chat_id,message_id,date,text FROM messages
                WHERE ({predicates}) AND COALESCE(is_deleted,0)=0
                  AND TRIM(COALESCE(text,''))<>'' AND COALESCE(date,'')<=?
                ORDER BY date DESC,chat_id DESC,message_id DESC LIMIT ?""",
            [*parameters, as_of, self.settings.context_max_raw_messages],
        ).fetchall()
        result = []
        for row in rows:
            item = {
                "chat_id": row[0],
                "source_chat_id": row[0],
                "message_id": row[1],
                "source_message_id": row[1],
                "date": row[2],
                "text": (row[3] or "")[:1200],
            }
            result.append(
                rank_item(
                    item, "evidence", direct_match=request.chat_id == row[0], now=as_of
                )
            )
        return highest(result, self.settings.context_max_raw_messages)

    def _global_state(self, as_of: str, historical: bool) -> dict:
        if historical:
            return {
                "as_of": as_of,
                "historical_fidelity": "partial: task, project, and open-loop lifecycle state is unavailable",
            }
        open_tasks, waiting = self.conn.execute(
            "SELECT SUM(CASE WHEN status='open' THEN 1 ELSE 0 END),SUM(CASE WHEN status='waiting' THEN 1 ELSE 0 END) FROM tasks WHERE status IN ('open','waiting') AND updated_at<=?",
            (as_of,),
        ).fetchone()
        projects = self.conn.execute(
            "SELECT COUNT(*),SUM(CASE WHEN status IN ('stale','critical','blocked') THEN 1 ELSE 0 END) FROM projects WHERE updated_at<=?",
            (as_of,),
        ).fetchone()
        attention = self.conn.execute(
            """SELECT p.canonical_name,COUNT(l.loop_id) FROM people AS p
               JOIN conversation_open_loops AS l ON l.person_id=p.person_id
               WHERE l.status IN ('open','waiting') GROUP BY p.person_id
               ORDER BY COUNT(l.loop_id) DESC,MAX(l.updated_at) DESC LIMIT 8"""
        ).fetchall()
        return {
            "as_of": as_of,
            "open_tasks": int(open_tasks or 0),
            "waiting_tasks": int(waiting or 0),
            "active_projects": int(projects[0] or 0),
            "at_risk_projects": int(projects[1] or 0),
            "people_requiring_attention": [
                {"name": row[0], "open_loops": int(row[1])} for row in attention
            ],
        }


def _alias_candidates(query: str) -> set[str]:
    """Generate a small exact-alias candidate set for an indexed lookup."""
    words = re.findall(r"[\w-]+", query, flags=re.UNICODE)[:12]
    candidates = {word for word in words if len(word) >= 3}
    for width in (2, 3):
        candidates.update(
            " ".join(words[index : index + width])
            for index in range(max(0, len(words) - width + 1))
        )
    return {candidate for candidate in candidates if len(candidate) >= 3}
