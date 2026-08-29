"""Conservative, evidence-backed context graph maintenance."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..utils import utc_now
from .repository import ensure_relationship


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class GraphImprovementReport:
    relationships_added: int
    affected_chats: int
    review_candidates_created: int
    diagnostics: dict[str, int | float]


class ContextGraphImprover:
    """Connect already-resolved canonical records; it does not guess identities.

    The improver only derives links from accepted task/entity records that share
    source evidence. Potential identity merges remain in the existing review
    queue, preserving the invariant that ambiguous people are never auto-merged.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def improve(
        self,
        *,
        entity_type: str | None = None,
        entity_id: int | None = None,
        source_chat_id: int | None = None,
    ) -> GraphImprovementReport:
        rows = self._anchored_tasks(entity_type, entity_id, source_chat_id)
        item_rows = self._accepted_item_links(entity_type, entity_id, source_chat_id)
        before = self.conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        affected_chats: set[int] = set()
        refresh_scopes: set[tuple[str, int]] = set()
        changed = False
        with self.conn:
            stale_chats = self._supersede_unsupported_relationships(
                entity_type, entity_id, source_chat_id
            )
            if stale_chats:
                changed = True
                affected_chats.update(stale_chats)
                refresh_scopes.update(
                    ("conversation", chat_id) for chat_id in stale_chats
                )
            for row in rows:
                (
                    task_id,
                    person_id,
                    company_id,
                    project_id,
                    chat_id,
                    item_id,
                    created,
                ) = row
                source_message_id = self._source_message_id(item_id)
                if person_id and project_id:
                    ensure_relationship(
                        self.conn,
                        "person",
                        int(person_id),
                        "project",
                        int(project_id),
                        "involved_in",
                        1.0,
                        chat_id,
                        source_message_id,
                        created,
                    )
                if company_id and project_id:
                    ensure_relationship(
                        self.conn,
                        "company",
                        int(company_id),
                        "project",
                        int(project_id),
                        "associated_with",
                        0.95,
                        chat_id,
                        source_message_id,
                        created,
                    )
                if project_id:
                    ensure_relationship(
                        self.conn,
                        "task",
                        int(task_id),
                        "project",
                        int(project_id),
                        "supports",
                        1.0,
                        chat_id,
                        source_message_id,
                        created,
                    )
                if chat_id is not None:
                    affected_chats.add(int(chat_id))
                    refresh_scopes.add(("conversation", int(chat_id)))
                for scope_type, scope_id in (
                    ("person", person_id),
                    ("company", company_id),
                    ("project", project_id),
                    ("task", task_id),
                ):
                    if scope_id is not None:
                        refresh_scopes.add((scope_type, int(scope_id)))
            for row in item_rows:
                (
                    person_id,
                    company_id,
                    project_id,
                    chat_id,
                    message_id,
                    occurred_at,
                    confidence,
                ) = row
                if person_id and project_id:
                    ensure_relationship(
                        self.conn,
                        "person",
                        int(person_id),
                        "project",
                        int(project_id),
                        "involved_in",
                        float(confidence),
                        chat_id,
                        message_id,
                        occurred_at,
                    )
                if company_id and project_id:
                    ensure_relationship(
                        self.conn,
                        "company",
                        int(company_id),
                        "project",
                        int(project_id),
                        "associated_with",
                        float(confidence),
                        chat_id,
                        message_id,
                        occurred_at,
                    )
                if chat_id is not None:
                    affected_chats.add(int(chat_id))
                    refresh_scopes.add(("conversation", int(chat_id)))
                for scope_type, scope_id in (
                    ("person", person_id),
                    ("company", company_id),
                    ("project", project_id),
                ):
                    if scope_id is not None:
                        refresh_scopes.add((scope_type, int(scope_id)))
            candidates = self._queue_contextual_candidates(source_chat_id)
            repair_candidates, repair_chats, repaired = self._repair_orphan_records(
                source_chat_id
            )
            candidates += repair_candidates
            affected_chats.update(repair_chats)
            if entity_type is None and entity_id is None and source_chat_id is None:
                repaired = self._repair_temporal_segments() or repaired
            changed = repaired
            after = self.conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[
                0
            ]
            added = int(after - before)
            if added or changed:
                refresh_scopes.update(
                    ("conversation", chat_id) for chat_id in repair_chats
                )
                refresh_scopes.add(("global", 0))
                from .refresh import enqueue_context_refresh

                enqueue_context_refresh(self.conn, refresh_scopes)
                self._bump_context_version()
        return GraphImprovementReport(
            added, len(affected_chats), candidates, graph_diagnostics(self.conn)
        )

    def _supersede_unsupported_relationships(
        self,
        entity_type: str | None,
        entity_id: int | None,
        source_chat_id: int | None,
    ) -> set[int]:
        """Close derived task/event links once their canonical project changes."""
        if entity_type is not None and source_chat_id is None:
            return set()
        filters = ["r.is_current=1"]
        parameters: list[object] = []
        if source_chat_id is not None:
            filters.append("r.source_chat_id=?")
            parameters.append(source_chat_id)
        if entity_type == "task" and entity_id is not None:
            filters.append("r.from_type='task' AND r.from_id=?")
            parameters.append(entity_id)
        now = utc_now()
        stale = self.conn.execute(
            f"""SELECT r.relationship_id,r.source_chat_id FROM relationships AS r
                JOIN tasks AS t ON r.from_type='task' AND r.from_id=t.task_id
                WHERE {" AND ".join(filters)} AND r.to_type='project'
                  AND r.relationship_type='supports'
                  AND (t.related_project_id IS NULL OR t.related_project_id<>r.to_id)
                UNION ALL
                SELECT r.relationship_id,r.source_chat_id FROM relationships AS r
                JOIN context_events AS e ON r.from_type='event' AND r.from_id=e.event_id
                WHERE {" AND ".join(filters)} AND r.to_type='project'
                  AND r.relationship_type='relates_to'
                  AND (e.project_id IS NULL OR e.project_id<>r.to_id)""",
            [*parameters, *parameters],
        ).fetchall()
        fact_links = self.conn.execute(
            f"""SELECT r.relationship_id,r.source_chat_id,r.to_id,f.valid_from
                FROM relationships AS r
                JOIN context_facts AS f ON r.from_type=f.subject_type
                  AND r.from_id=f.subject_id
                WHERE {" AND ".join(filters)} AND r.to_type='project'
                  AND r.relationship_type='context_fact_about'
                  AND r.confidence<1.0""",
            parameters,
        ).fetchall()
        for relationship_id, chat_id, project_id, occurred_at in fact_links:
            if chat_id is None:
                continue
            candidate = self._local_project_consensus(int(chat_id), str(occurred_at))
            if candidate is None or candidate[0] != int(project_id):
                stale.append((relationship_id, chat_id))
        if not stale:
            return set()
        self.conn.executemany(
            """UPDATE relationships SET valid_to=?,is_current=0,updated_at=?
               WHERE relationship_id=?""",
            [(now, now, int(row[0])) for row in stale],
        )
        return {int(row[1]) for row in stale if row[1] is not None}

    def improve_global(self) -> GraphImprovementReport:
        return self.improve()

    def improve_person(self, person_id: int) -> GraphImprovementReport:
        report = self.improve(entity_type="person", entity_id=person_id)
        # Graph repair and contact materialization are distinct views over the
        # same accepted evidence; refreshing here keeps targeted improvement
        # useful without introducing a second graph.
        from .conversation import ConversationContextService

        ConversationContextService(self.conn, None).refresh_person(person_id)
        return report

    def improve_company(self, company_id: int) -> GraphImprovementReport:
        return self.improve(entity_type="company", entity_id=company_id)

    def improve_project(self, project_id: int) -> GraphImprovementReport:
        return self.improve(entity_type="project", entity_id=project_id)

    def improve_task(self, task_id: int) -> GraphImprovementReport:
        """Repair only the task's evidence neighbourhood, not the whole graph."""
        row = self.conn.execute(
            "SELECT source_chat_id,related_person_id,related_company_id,related_project_id FROM tasks WHERE task_id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Task {task_id} was not found.")
        chat_id, person_id, company_id, project_id = row
        if project_id is not None:
            return self.improve(
                entity_type="project", entity_id=int(project_id), source_chat_id=chat_id
            )
        if person_id is not None:
            return self.improve(
                entity_type="person", entity_id=int(person_id), source_chat_id=chat_id
            )
        if company_id is not None:
            return self.improve(
                entity_type="company", entity_id=int(company_id), source_chat_id=chat_id
            )
        return self.improve(source_chat_id=chat_id)

    def discover_cross_chat_candidates(self, *, limit: int = 40) -> int:
        """Queue bounded, source-backed cross-chat project candidates for Review.

        This selector deliberately does not call ``improve()``: it creates
        Review candidates only and never mutates canonical rows or graph edges.
        A candidate requires the same resolved person in two different chats,
        exact source messages, and project evidence no more than 90 days away.
        """
        if not 1 <= limit <= 80:
            raise ValueError("Cross-chat discovery limit must be between 1 and 80")
        rows = self.conn.execute(
            """SELECT candidate.item_id,candidate.person_id,candidate.source_chat_id,
                      candidate.source_message_id,candidate.source_date,
                      candidate.confidence,anchor.item_id,anchor.project_id,
                      anchor.source_chat_id,anchor.source_message_id,
                      anchor.source_date,anchor.confidence
                 FROM ai_items AS candidate
                 JOIN ai_items AS anchor ON anchor.person_id=candidate.person_id
                 JOIN messages AS candidate_message
                   ON candidate_message.chat_id=candidate.source_chat_id
                  AND candidate_message.message_id=candidate.source_message_id
                 JOIN messages AS anchor_message
                   ON anchor_message.chat_id=anchor.source_chat_id
                  AND anchor_message.message_id=anchor.source_message_id
                WHERE candidate.person_id IS NOT NULL
                  AND candidate.project_id IS NULL
                  AND candidate.source_chat_id IS NOT NULL
                  AND candidate.source_message_id IS NOT NULL
                  AND candidate.source_date IS NOT NULL
                  AND candidate.confidence>=0.90
                  AND COALESCE(candidate_message.is_deleted,0)=0
                  AND anchor.project_id IS NOT NULL
                  AND anchor.source_chat_id IS NOT NULL
                  AND anchor.source_message_id IS NOT NULL
                  AND anchor.source_date IS NOT NULL
                  AND anchor.confidence>=0.90
                  AND COALESCE(anchor_message.is_deleted,0)=0
                  AND anchor.source_chat_id<>candidate.source_chat_id
                  AND NOT EXISTS (
                      SELECT 1 FROM user_feedback AS feedback
                       WHERE feedback.entity_type='ai_item'
                         AND feedback.entity_id=candidate.item_id
                         AND feedback.feedback_type LIKE 'review:%'
                         AND json_extract(feedback.payload_json, '$.action')
                             IN ('reject','ignore')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM user_feedback AS feedback
                       WHERE feedback.entity_type='ai_item'
                         AND feedback.entity_id=anchor.item_id
                         AND feedback.feedback_type LIKE 'review:%'
                         AND json_extract(feedback.payload_json, '$.action')
                             IN ('reject','ignore')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM relationships AS relationship
                       WHERE relationship.is_current=1
                         AND (
                             (relationship.from_type='person'
                              AND relationship.from_id=candidate.person_id
                              AND relationship.to_type='project'
                              AND relationship.to_id=anchor.project_id)
                             OR
                             (relationship.to_type='person'
                              AND relationship.to_id=candidate.person_id
                              AND relationship.from_type='project'
                              AND relationship.from_id=anchor.project_id)
                         )
                  )
                ORDER BY candidate.source_date DESC,candidate.item_id DESC,
                         anchor.source_date DESC,anchor.item_id DESC
                LIMIT ?""",
            (limit * 4,),
        ).fetchall()
        created = 0
        for row in rows:
            (
                candidate_id,
                person_id,
                candidate_chat_id,
                candidate_message_id,
                candidate_at,
                candidate_confidence,
                anchor_id,
                project_id,
                anchor_chat_id,
                anchor_message_id,
                anchor_at,
                anchor_confidence,
            ) = row
            candidate_time = _parse_timestamp(str(candidate_at))
            anchor_time = _parse_timestamp(str(anchor_at))
            if (
                candidate_time is None
                or anchor_time is None
                or abs(candidate_time - anchor_time) > timedelta(days=90)
            ):
                continue
            exists = self.conn.execute(
                """SELECT 1 FROM review_queue WHERE review_type='graph_link'
                   AND subject_type='ai_item' AND subject_id=?
                   AND json_extract(payload_json, '$.candidate_project_id')=? LIMIT 1""",
                (candidate_id, project_id),
            ).fetchone()
            if exists:
                continue
            confidence = min(float(candidate_confidence), float(anchor_confidence))
            self.conn.execute(
                """INSERT INTO review_queue(
                       review_type,subject_type,subject_id,payload_json,confidence,created_at
                   ) VALUES ('graph_link','ai_item',?,?,?,?)""",
                (
                    candidate_id,
                    json.dumps(
                        {
                            "source_item_id": candidate_id,
                            "chat_id": candidate_chat_id,
                            "message_id": candidate_message_id,
                            "candidate_project_id": project_id,
                            "candidate_kind": "cross_chat_relationship",
                            "relationship_path": [
                                {"entity_type": "person", "entity_id": person_id},
                                {"entity_type": "project", "entity_id": project_id},
                            ],
                            "candidate_evidence": [
                                {
                                    "source_item_id": anchor_id,
                                    "chat_id": anchor_chat_id,
                                    "message_id": anchor_message_id,
                                }
                            ],
                            "reasons": [
                                "same resolved person across distinct chats",
                                "project evidence is within 90 days",
                            ],
                        },
                        sort_keys=True,
                    ),
                    confidence,
                    utc_now(),
                ),
            )
            created += 1
            if created >= limit:
                break
        return created

    def _accepted_item_links(
        self,
        entity_type: str | None,
        entity_id: int | None,
        source_chat_id: int | None,
    ) -> list[tuple]:
        predicates = [
            "confidence >= 0.90",
            "project_id IS NOT NULL",
            "NOT EXISTS (SELECT 1 FROM user_feedback AS f "
            "WHERE f.entity_type='ai_item' AND f.entity_id=ai_items.item_id "
            "AND f.feedback_type LIKE 'review:%' "
            "AND json_extract(f.payload_json, '$.action') IN ('reject','ignore'))",
        ]
        parameters: list[object] = []
        if entity_type and entity_id is not None:
            column = {
                "person": "person_id",
                "company": "company_id",
                "project": "project_id",
            }.get(entity_type)
            if column is None:
                raise ValueError(
                    "Targeted graph improvement requires person, company, or project."
                )
            predicates.append(f"{column}=?")
            parameters.append(entity_id)
        if source_chat_id is not None:
            predicates.append("source_chat_id=?")
            parameters.append(source_chat_id)
        return self.conn.execute(
            f"""SELECT person_id,company_id,project_id,source_chat_id,source_message_id,
                       source_date,confidence
                FROM ai_items WHERE {" AND ".join(predicates)}""",
            parameters,
        ).fetchall()

    def _queue_contextual_candidates(self, source_chat_id: int | None) -> int:
        """Surface a possible chat-project link without silently accepting it."""
        predicates = [
            "i.project_id IS NULL",
            "i.confidence >= 0.90",
            "mc.importance IN ('critical','high')",
        ]
        parameters: list[object] = []
        if source_chat_id is not None:
            predicates.append("i.source_chat_id=?")
            parameters.append(source_chat_id)
        rows = self.conn.execute(
            f"""SELECT i.item_id,i.source_chat_id,i.source_message_id,i.source_date,
                       i.confidence
                FROM ai_items AS i
                JOIN message_classifications AS mc
                  ON mc.chat_id=i.source_chat_id AND mc.message_id=i.source_message_id
                WHERE {" AND ".join(predicates)}""",
            parameters,
        ).fetchall()
        created = 0
        for item_id, chat_id, message_id, occurred_at, confidence in rows:
            candidate = self._local_project_consensus(
                int(chat_id), str(occurred_at) if occurred_at else None
            )
            if candidate is None:
                continue
            project_id, _anchor_count = candidate
            exists = self.conn.execute(
                """SELECT 1 FROM review_queue WHERE review_type='graph_link'
                   AND json_extract(payload_json, '$.source_item_id')=? LIMIT 1""",
                (item_id,),
            ).fetchone()
            if exists:
                continue
            self.conn.execute(
                """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,confidence,created_at)
                   VALUES ('graph_link','ai_item',?,json_object('source_item_id',?,'chat_id',?,'message_id',?,'candidate_project_id',?),?,?)""",
                (
                    item_id,
                    item_id,
                    chat_id,
                    message_id,
                    project_id,
                    confidence,
                    utc_now(),
                ),
            )
            created += 1
        return created

    def _repair_orphan_records(
        self, source_chat_id: int | None
    ) -> tuple[int, set[int], bool]:
        """Repair only evidence with a strong, local project consensus.

        Two independently anchored tasks for one project make a source chat a
        high-confidence neighbourhood. One anchor is useful but reviewable;
        competing projects remain untouched. This deliberately avoids lexical
        matching and never changes entities or raw evidence.
        """
        candidates = 0
        affected: set[int] = set()
        changed = False
        chat_ids = self._repair_chat_ids(source_chat_id)
        for chat_id in chat_ids:
            task_rows = self.conn.execute(
                """SELECT t.task_id,i.source_chat_id,i.source_message_id,
                          COALESCE(i.source_date,t.created_at)
                   FROM tasks AS t LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id
                   WHERE t.source_chat_id=? AND t.status IN ('open','waiting')
                     AND t.related_person_id IS NULL AND t.related_company_id IS NULL
                     AND t.related_project_id IS NULL""",
                (chat_id,),
            ).fetchall()
            event_rows = self.conn.execute(
                """SELECT event_id,source_chat_id,source_message_id,
                          COALESCE(occurred_at,observed_at,created_at)
                   FROM context_events
                   WHERE source_chat_id=? AND project_id IS NULL
                     AND person_id IS NULL AND company_id IS NULL AND task_id IS NULL""",
                (chat_id,),
            ).fetchall()
            fact_rows = self.conn.execute(
                """SELECT f.fact_id,f.subject_type,f.subject_id,f.source_chat_id,
                          f.source_message_id,f.valid_from FROM context_facts AS f
                   WHERE f.source_chat_id=? AND f.subject_type IN ('person','company')
                """,
                (chat_id,),
            ).fetchall()
            if not task_rows and not event_rows and not fact_rows:
                continue
            for task_id, record_chat_id, message_id, occurred_at in task_rows:
                candidate = self._local_project_consensus(chat_id, occurred_at)
                if candidate is None:
                    continue
                project_id, anchor_count = candidate
                if self._has_project_relationship("task", int(task_id), project_id):
                    continue
                if anchor_count >= 2 and not self._rejected_link(
                    "task", int(task_id), project_id
                ):
                    self.conn.execute(
                        "UPDATE tasks SET related_project_id=?,updated_at=? WHERE task_id=?",
                        (project_id, utc_now(), task_id),
                    )
                    ensure_relationship(
                        self.conn,
                        "task",
                        int(task_id),
                        "project",
                        project_id,
                        "supports",
                        0.95,
                        record_chat_id,
                        message_id,
                        occurred_at,
                    )
                    changed = True
                    affected.add(chat_id)
                else:
                    candidates += self._queue_repair_candidate(
                        "graph_task_link", "task", int(task_id), chat_id, project_id
                    )
            for event_id, record_chat_id, message_id, occurred_at in event_rows:
                candidate = self._local_project_consensus(chat_id, occurred_at)
                if candidate is None:
                    continue
                project_id, anchor_count = candidate
                if anchor_count >= 2 and not self._rejected_link(
                    "context_event", int(event_id), project_id
                ):
                    self.conn.execute(
                        "UPDATE context_events SET project_id=? WHERE event_id=?",
                        (project_id, event_id),
                    )
                    ensure_relationship(
                        self.conn,
                        "event",
                        int(event_id),
                        "project",
                        project_id,
                        "relates_to",
                        0.95,
                        record_chat_id,
                        message_id,
                        occurred_at,
                    )
                    changed = True
                    affected.add(chat_id)
                else:
                    candidates += self._queue_repair_candidate(
                        "graph_event_link",
                        "context_event",
                        int(event_id),
                        chat_id,
                        project_id,
                    )
            for (
                fact_id,
                subject_type,
                subject_id,
                record_chat_id,
                message_id,
                occurred_at,
            ) in fact_rows:
                candidate = self._local_project_consensus(chat_id, occurred_at)
                if candidate is None:
                    continue
                project_id, anchor_count = candidate
                if self._has_project_relationship(
                    str(subject_type), int(subject_id), project_id
                ):
                    continue
                if anchor_count >= 2 and not self._rejected_link(
                    "context_fact", int(fact_id), project_id
                ):
                    ensure_relationship(
                        self.conn,
                        str(subject_type),
                        int(subject_id),
                        "project",
                        project_id,
                        "context_fact_about",
                        0.95,
                        record_chat_id,
                        message_id,
                        occurred_at,
                    )
                    changed = True
                    affected.add(chat_id)
                else:
                    candidates += self._queue_repair_candidate(
                        "graph_fact_link",
                        "context_fact",
                        int(fact_id),
                        chat_id,
                        project_id,
                    )
        return candidates, affected, changed

    def _repair_temporal_segments(self) -> bool:
        """Restore obvious fact intervals without changing their values or sources."""
        changed = False
        now = utc_now()
        groups = self.conn.execute(
            """SELECT subject_type,subject_id,predicate
               FROM context_facts GROUP BY subject_type,subject_id,predicate
               HAVING COUNT(*) > 1"""
        ).fetchall()
        for subject_type, subject_id, predicate in groups:
            rows = self.conn.execute(
                """SELECT fact_id,valid_from,valid_to,is_current,superseded_by_fact_id
                   FROM context_facts WHERE subject_type=? AND subject_id=? AND predicate=?
                   ORDER BY valid_from,fact_id""",
                (subject_type, subject_id, predicate),
            ).fetchall()
            if len({row[1] for row in rows}) != len(rows):
                continue
            for index, row in enumerate(rows):
                fact_id, _, valid_to, is_current, superseded_by = row
                next_row = rows[index + 1] if index + 1 < len(rows) else None
                expected = (
                    str(next_row[1]) if next_row else None,
                    int(next_row is None),
                    int(next_row[0]) if next_row else None,
                )
                if (valid_to, int(is_current), superseded_by) == expected:
                    continue
                self.conn.execute(
                    """UPDATE context_facts
                       SET valid_to=?,is_current=?,superseded_by_fact_id=?,updated_at=?
                       WHERE fact_id=?""",
                    (*expected, now, fact_id),
                )
                changed = True
        return changed

    def _repair_chat_ids(self, source_chat_id: int | None) -> list[int]:
        if source_chat_id is not None:
            return [source_chat_id]
        return [
            int(row[0])
            for row in self.conn.execute(
                """SELECT DISTINCT source_chat_id FROM tasks
                   WHERE source_chat_id IS NOT NULL AND related_project_id IS NOT NULL
                   ORDER BY source_chat_id LIMIT 80"""
            )
        ]

    def _local_project_consensus(
        self, chat_id: int, occurred_at: str | None
    ) -> tuple[int, int] | None:
        """Return one nearby project supported by distinct source messages only."""
        when = _parse_timestamp(occurred_at)
        if when is None:
            return None
        anchors: dict[int, set[int]] = {}
        rows = self.conn.execute(
            """SELECT t.related_project_id,i.source_message_id,
                      COALESCE(i.source_date,t.created_at)
               FROM tasks AS t JOIN ai_items AS i ON i.item_id=t.source_item_id
               WHERE t.source_chat_id=? AND t.related_project_id IS NOT NULL
                 AND i.source_message_id IS NOT NULL
               ORDER BY t.task_id DESC LIMIT 160""",
            (chat_id,),
        ).fetchall()
        for project_id, message_id, anchor_at in rows:
            anchor_time = _parse_timestamp(str(anchor_at) if anchor_at else None)
            if anchor_time is None or abs(anchor_time - when) > timedelta(days=90):
                continue
            anchors.setdefault(int(project_id), set()).add(int(message_id))
        if len(anchors) != 1:
            return None
        project_id, messages = next(iter(anchors.items()))
        return project_id, len(messages)

    def _has_project_relationship(
        self, subject_type: str, subject_id: int, project_id: int
    ) -> bool:
        return bool(
            self.conn.execute(
                """SELECT 1 FROM relationships WHERE is_current=1 AND
                   ((from_type=? AND from_id=? AND to_type='project' AND to_id=?)
                    OR (to_type=? AND to_id=? AND from_type='project' AND from_id=?))
                   LIMIT 1""",
                (
                    subject_type,
                    subject_id,
                    project_id,
                    subject_type,
                    subject_id,
                    project_id,
                ),
            ).fetchone()
        )

    def _queue_repair_candidate(
        self,
        review_type: str,
        subject_type: str,
        subject_id: int,
        chat_id: int,
        project_id: int,
    ) -> int:
        exists = self.conn.execute(
            """SELECT 1 FROM review_queue WHERE review_type=? AND subject_type=?
               AND subject_id=? AND json_extract(payload_json, '$.candidate_project_id')=? LIMIT 1""",
            (review_type, subject_type, subject_id, project_id),
        ).fetchone()
        if exists or self._rejected_link(subject_type, subject_id, project_id):
            return 0
        self.conn.execute(
            """INSERT INTO review_queue(review_type,subject_type,subject_id,payload_json,confidence,created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                review_type,
                subject_type,
                subject_id,
                json.dumps({"chat_id": chat_id, "candidate_project_id": project_id}),
                0.75,
                utc_now(),
            ),
        )
        return 1

    def _rejected_link(
        self, subject_type: str, subject_id: int, project_id: int
    ) -> bool:
        return (
            self.conn.execute(
                """SELECT 1 FROM user_feedback
               WHERE feedback_type LIKE 'review:%' AND entity_type=? AND entity_id=?
                 AND json_extract(payload_json, '$.action') IN ('reject','ignore')
                 AND json_extract(payload_json, '$.payload.candidate_project_id')=? LIMIT 1""",
                (subject_type, subject_id, project_id),
            ).fetchone()
            is not None
        )

    def _anchored_tasks(
        self,
        entity_type: str | None,
        entity_id: int | None,
        source_chat_id: int | None,
    ) -> list[tuple]:
        predicates = [
            "(related_person_id IS NOT NULL OR related_company_id IS NOT NULL OR related_project_id IS NOT NULL)"
        ]
        parameters: list[object] = []
        if entity_type and entity_id is not None:
            column = {
                "person": "related_person_id",
                "company": "related_company_id",
                "project": "related_project_id",
            }.get(entity_type)
            if column is None:
                raise ValueError(
                    "Targeted graph improvement requires person, company, or project."
                )
            predicates.append(f"{column}=?")
            parameters.append(entity_id)
        if source_chat_id is not None:
            predicates.append("source_chat_id=?")
            parameters.append(source_chat_id)
        return self.conn.execute(
            f"""SELECT task_id,related_person_id,related_company_id,related_project_id,
                       source_chat_id,source_item_id,created_at
                FROM tasks WHERE {" AND ".join(predicates)}""",
            parameters,
        ).fetchall()

    def _source_message_id(self, item_id: int | None) -> int | None:
        if item_id is None:
            return None
        row = self.conn.execute(
            "SELECT source_message_id FROM ai_items WHERE item_id=?", (item_id,)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def _bump_context_version(self) -> None:
        row = self.conn.execute(
            "SELECT value FROM app_meta WHERE key='context_graph_version'"
        ).fetchone()
        version = int(row[0]) + 1 if row else 2
        now = utc_now()
        self.conn.execute(
            """INSERT INTO app_meta(key,value,updated_at) VALUES ('context_graph_version',?,?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (str(version), now),
        )


def graph_diagnostics(conn: sqlite3.Connection) -> dict[str, int | float]:
    entities = int(
        conn.execute(
            "SELECT (SELECT COUNT(*) FROM people)+(SELECT COUNT(*) FROM companies)+(SELECT COUNT(*) FROM projects)"
        ).fetchone()[0]
        or 0
    )
    relationships = int(
        conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0] or 0
    )
    orphan_tasks = int(
        conn.execute(
            """SELECT COUNT(*) FROM tasks WHERE status IN ('open','waiting')
               AND related_person_id IS NULL AND related_company_id IS NULL AND related_project_id IS NULL"""
        ).fetchone()[0]
        or 0
    )
    orphan_important = int(
        conn.execute(
            """SELECT COUNT(*) FROM message_classifications AS mc
               LEFT JOIN ai_items AS i ON i.source_chat_id=mc.chat_id AND i.source_message_id=mc.message_id
               WHERE mc.importance IN ('critical','high') AND i.item_id IS NULL"""
        ).fetchone()[0]
        or 0
    )
    merge_candidates = int(
        conn.execute("SELECT COUNT(*) FROM entity_merge_candidates").fetchone()[0] or 0
    )
    graph_candidates = int(
        conn.execute(
            "SELECT COUNT(*) FROM review_queue WHERE review_type='graph_link' AND status='pending'"
        ).fetchone()[0]
        or 0
    )
    temporal_segments = int(
        conn.execute(
            """SELECT COUNT(*) FROM context_facts
               WHERE (valid_to IS NOT NULL AND valid_to <= valid_from)
                  OR (is_current=1 AND valid_to IS NOT NULL)"""
        ).fetchone()[0]
        or 0
    )
    stale_classifications = int(
        conn.execute(
            "SELECT COUNT(*) FROM message_classifications WHERE context_stale=1"
        ).fetchone()[0]
        or 0
    )
    stale_analyses = int(
        conn.execute(
            "SELECT COUNT(*) FROM ai_message_state WHERE analysis_stale=1"
        ).fetchone()[0]
        or 0
    )
    unclassified_messages = int(
        conn.execute(
            """SELECT COUNT(*) FROM messages AS m
               LEFT JOIN message_classifications AS mc
                 ON mc.chat_id=m.chat_id AND mc.message_id=m.message_id
               WHERE COALESCE(m.is_deleted,0)=0 AND TRIM(COALESCE(m.text,''))<>''
                 AND mc.chat_id IS NULL"""
        ).fetchone()[0]
        or 0
    )
    route_counts = conn.execute(
        """SELECT
               SUM(CASE WHEN route='archive' THEN 1 ELSE 0 END),
               SUM(CASE WHEN route='news' THEN 1 ELSE 0 END),
               SUM(CASE WHEN route='operational' THEN 1 ELSE 0 END),
               SUM(CASE WHEN route='state_change' THEN 1 ELSE 0 END),
               SUM(CASE WHEN route='contextual' THEN 1 ELSE 0 END)
          FROM (
              SELECT CASE
                  WHEN importance='noise' OR content_type='spam' THEN 'archive'
                  WHEN information_scope='external_news' THEN 'news'
                  WHEN content_type IN ('request','promise','payment','meeting') THEN 'operational'
                  WHEN content_type='decision' THEN 'state_change'
                  ELSE 'contextual'
              END AS route
              FROM message_classifications
          )
        """
    ).fetchone()
    archived, news, operational, state_change, contextual = (
        int(value or 0) for value in route_counts
    )
    orphan_segments = int(
        conn.execute(
            """SELECT COUNT(*) FROM conversation_segments AS s
               WHERE NOT EXISTS (
                   SELECT 1 FROM tasks AS t WHERE t.source_chat_id=s.chat_id
                     AND t.related_project_id=s.project_id
               )"""
        ).fetchone()[0]
        or 0
    )
    return {
        "entities": entities,
        "relationships": relationships,
        "orphan_tasks": orphan_tasks,
        "orphan_important_messages": orphan_important,
        "merge_candidates": merge_candidates,
        "graph_link_candidates": graph_candidates,
        "temporal_segment_anomalies": temporal_segments,
        "stale_classifications": stale_classifications,
        "stale_analyses": stale_analyses,
        "unclassified_messages": unclassified_messages,
        "route_archive_only": archived,
        "route_news_memory": news,
        "route_operational": operational,
        "route_state_change": state_change,
        "route_contextual_memory": contextual,
        "orphan_conversation_segments": orphan_segments,
    }
