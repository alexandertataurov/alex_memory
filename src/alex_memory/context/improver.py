"""Conservative, evidence-backed context graph maintenance."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ..utils import utc_now
from .repository import ensure_relationship


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
        changed = False
        with self.conn:
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
            candidates = self._queue_contextual_candidates(source_chat_id)
            repair_candidates, repair_chats, repaired = self._repair_orphan_records(
                source_chat_id
            )
            candidates += repair_candidates
            affected_chats.update(repair_chats)
            changed = repaired or self._repair_temporal_segments()
            after = self.conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[
                0
            ]
            added = int(after - before)
            if added or changed:
                self._mark_affected_analysis_stale(affected_chats)
                self._bump_context_version()
        return GraphImprovementReport(
            added, len(affected_chats), candidates, graph_diagnostics(self.conn)
        )

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

    def _accepted_item_links(
        self,
        entity_type: str | None,
        entity_id: int | None,
        source_chat_id: int | None,
    ) -> list[tuple]:
        predicates = ["confidence >= 0.90", "project_id IS NOT NULL"]
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
            f"""SELECT i.item_id,i.source_chat_id,i.source_message_id,
                       chat_project.project_id,i.confidence
                FROM ai_items AS i
                JOIN message_classifications AS mc
                  ON mc.chat_id=i.source_chat_id AND mc.message_id=i.source_message_id
                JOIN (
                    SELECT source_chat_id,MIN(related_project_id) AS project_id
                    FROM tasks WHERE related_project_id IS NOT NULL
                    GROUP BY source_chat_id
                    HAVING COUNT(DISTINCT related_project_id)=1
                ) AS chat_project ON chat_project.source_chat_id=i.source_chat_id
                WHERE {" AND ".join(predicates)}""",
            parameters,
        ).fetchall()
        created = 0
        for item_id, chat_id, message_id, project_id, confidence in rows:
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
        consensus = self._chat_project_consensus(source_chat_id)
        candidates = 0
        affected: set[int] = set()
        changed = False
        for chat_id, project_id, anchor_count in consensus:
            task_rows = self.conn.execute(
                """SELECT task_id FROM tasks
                   WHERE source_chat_id=? AND status IN ('open','waiting')
                     AND related_person_id IS NULL AND related_company_id IS NULL
                     AND related_project_id IS NULL""",
                (chat_id,),
            ).fetchall()
            event_rows = self.conn.execute(
                """SELECT event_id FROM context_events
                   WHERE source_chat_id=? AND project_id IS NULL
                     AND person_id IS NULL AND company_id IS NULL AND task_id IS NULL""",
                (chat_id,),
            ).fetchall()
            fact_rows = self.conn.execute(
                """SELECT f.fact_id,f.subject_type,f.subject_id FROM context_facts AS f
                   WHERE f.source_chat_id=? AND f.subject_type IN ('person','company')
                     AND NOT EXISTS (
                         SELECT 1 FROM relationships AS r
                         WHERE ((r.from_type=f.subject_type AND r.from_id=f.subject_id
                                 AND r.to_type='project' AND r.to_id=?)
                             OR (r.to_type=f.subject_type AND r.to_id=f.subject_id
                                 AND r.from_type='project' AND r.from_id=?))
                           AND r.is_current=1
                     )""",
                (chat_id, project_id, project_id),
            ).fetchall()
            if not task_rows and not event_rows and not fact_rows:
                continue
            if anchor_count >= 2:
                for (task_id,) in task_rows:
                    if self._rejected_link("task", int(task_id), project_id):
                        continue
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
                        chat_id,
                        None,
                        utc_now(),
                    )
                    changed = True
                for (event_id,) in event_rows:
                    if self._rejected_link("context_event", int(event_id), project_id):
                        continue
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
                        chat_id,
                        None,
                        utc_now(),
                    )
                    changed = True
                for fact_id, subject_type, subject_id in fact_rows:
                    if self._rejected_link("context_fact", int(fact_id), project_id):
                        continue
                    ensure_relationship(
                        self.conn,
                        str(subject_type),
                        int(subject_id),
                        "project",
                        project_id,
                        "context_fact_about",
                        0.95,
                        chat_id,
                        None,
                        utc_now(),
                    )
                    changed = True
                if changed:
                    affected.add(chat_id)
                continue
            for (task_id,) in task_rows:
                candidates += self._queue_repair_candidate(
                    "graph_task_link", "task", int(task_id), chat_id, project_id
                )
            for (event_id,) in event_rows:
                candidates += self._queue_repair_candidate(
                    "graph_event_link",
                    "context_event",
                    int(event_id),
                    chat_id,
                    project_id,
                )
            for fact_id, _, _ in fact_rows:
                candidates += self._queue_repair_candidate(
                    "graph_fact_link", "context_fact", int(fact_id), chat_id, project_id
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

    def _chat_project_consensus(
        self, source_chat_id: int | None
    ) -> list[tuple[int, int, int]]:
        predicates = ["source_chat_id IS NOT NULL", "related_project_id IS NOT NULL"]
        parameters: list[object] = []
        if source_chat_id is not None:
            predicates.append("source_chat_id=?")
            parameters.append(source_chat_id)
        return [
            (int(chat_id), int(project_id), int(anchor_count))
            for chat_id, project_id, anchor_count in self.conn.execute(
                f"""SELECT source_chat_id,MIN(related_project_id),COUNT(*)
                    FROM tasks WHERE {" AND ".join(predicates)}
                    GROUP BY source_chat_id
                    HAVING COUNT(DISTINCT related_project_id)=1""",
                parameters,
            )
        ]

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

    def _mark_affected_analysis_stale(self, chat_ids: set[int]) -> None:
        if not chat_ids:
            return
        placeholders = ",".join("?" for _ in chat_ids)
        self.conn.execute(
            f"UPDATE message_classifications SET context_stale=1 WHERE chat_id IN ({placeholders}) AND importance IN ('critical','high')",
            sorted(chat_ids),
        )
        self.conn.execute(
            f"""UPDATE ai_message_state SET analysis_stale=1
                WHERE chat_id IN ({placeholders})
                  AND EXISTS (
                      SELECT 1 FROM message_classifications AS mc
                      WHERE mc.chat_id=ai_message_state.chat_id
                        AND mc.message_id=ai_message_state.message_id
                        AND mc.importance IN ('critical','high')
                  )""",
            sorted(chat_ids),
        )

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
               SUM(CASE WHEN importance='noise' OR content_type='spam' THEN 1 ELSE 0 END),
               SUM(CASE WHEN information_scope='external_news' THEN 1 ELSE 0 END),
               SUM(CASE WHEN content_type IN ('request','promise','payment','meeting') THEN 1 ELSE 0 END),
               SUM(CASE WHEN content_type='decision' THEN 1 ELSE 0 END),
               COUNT(*)
           FROM message_classifications"""
    ).fetchone()
    archived, news, operational, state_change, classified = (
        int(value or 0) for value in route_counts
    )
    contextual = max(0, classified - archived - news - operational - state_change)
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
    covered = max(0, entities - orphan_tasks)
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
        "heuristic_coverage": round(covered / entities * 100, 1) if entities else 100.0,
    }
