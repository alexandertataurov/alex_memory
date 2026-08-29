from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import replace
from datetime import datetime

from ...config import Settings
from ...context import ContextBuilder, ContextRequest
from ...telegram.evidence import TelegramEvidenceSource
from ...utils import utc_now
from .models import EvidenceItem, TaskDeepDiveReport
from .retrieval import (
    lifecycle_evidence,
    raw_message_evidence,
    structured_evidence,
    task_event_evidence,
    task_concepts,
)


class TaskDeepDiveService:
    """Build and extend a bounded investigation without treating inference as evidence."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn, self.settings = conn, settings

    def build(
        self, task_id: int, *, as_of: datetime | None = None, deeper: bool = False
    ) -> TaskDeepDiveReport:
        if as_of is not None:
            raise ValueError(
                "Historical Task Deep Dive is unavailable until task lifecycle state can be reconstructed."
            )
        task = self._task(task_id)
        as_of_text = (
            as_of.isoformat() if as_of else datetime.now().astimezone().isoformat()
        )
        context = self._context(
            task_id, f"{task['title']} {task.get('details') or ''}", as_of
        )
        concepts = task_concepts(task, context)
        if deeper:
            concepts = task_concepts(
                task, context, self._discovered_terms(task_id, as_of_text)
            )
        evidence = [
            *structured_evidence(task, context),
            *task_event_evidence(self.conn, task_id, as_of_text),
            *lifecycle_evidence(self.conn, task_id, as_of_text),
            *self._origin_evidence(task, as_of_text),
        ]
        raw, concepts, diagnostics = self._iterative_raw_evidence(
            task, context, concepts, as_of_text
        )
        evidence = self._dedupe_and_limit([*evidence, *raw])
        session_id = self._save_session(
            task_id,
            concepts,
            evidence,
            query=None,
            mode="build",
            as_of=as_of_text,
            diagnostics=diagnostics,
        )
        return self._report(
            task, context, concepts, evidence, session_id, as_of_text, diagnostics
        )

    def search(
        self, task_id: int, query: str, *, as_of: datetime | None = None
    ) -> TaskDeepDiveReport:
        report = self.build(task_id, as_of=as_of)
        task = report.task
        context = self._context(task_id, query, as_of)
        concepts = task_concepts(task, context, [query])
        raw, concepts, diagnostics = self._iterative_raw_evidence(
            task, context, concepts, report.as_of
        )
        evidence = self._dedupe_and_limit([*report.evidence, *raw])
        session_id = self._save_session(
            task_id,
            concepts,
            evidence,
            previous_session=report.session_id,
            query=query,
            mode="search",
            as_of=report.as_of,
            diagnostics=diagnostics,
        )
        return self._report(
            task, context, concepts, evidence, session_id, report.as_of, diagnostics
        )

    def ask(self, task_id: int, question: str) -> tuple[str, list[EvidenceItem]]:
        report = self.search(task_id, question)
        terms = {word for word in question.casefold().split() if len(word) > 2}
        matched = [
            item
            for item in report.evidence
            if terms.intersection(item.text.casefold().split())
        ]
        sources = (matched or report.evidence)[:5]
        if not sources:
            return "No source-backed evidence was found for this task yet.", []
        answer = "\n".join(f"- {item.text[:500]} [{item.citation}]" for item in sources)
        return answer, sources

    def add_note(self, task_id: int, content: str) -> int:
        text = content.strip()
        if not text:
            raise ValueError("A task note cannot be blank.")
        now = utc_now()
        cursor = self.conn.execute(
            "INSERT INTO task_notes(task_id,content,created_at,updated_at) VALUES (?,?,?,?)",
            (task_id, text, now, now),
        )
        self.conn.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    def pin_evidence(self, task_id: int, evidence_id: str) -> None:
        owned = self.conn.execute(
            """SELECT 1 FROM task_deep_dive_sessions AS session
               JOIN task_deep_dive_evidence AS evidence
                 ON evidence.session_id=session.session_id
               WHERE session.task_id=? AND evidence.evidence_id=? LIMIT 1""",
            (task_id, evidence_id),
        ).fetchone()
        if owned is None:
            raise ValueError(
                "Evidence is not part of an investigation session for this task."
            )
        self.conn.execute(
            "INSERT OR IGNORE INTO task_deep_dive_pins(task_id,evidence_id,created_at) VALUES (?,?,?)",
            (task_id, evidence_id, utc_now()),
        )
        self.conn.commit()

    def _task(self, task_id: int) -> dict:
        row = self.conn.execute(
            """SELECT t.task_id,t.title,t.details,t.status,t.owner,t.due_date,t.related_person_id,t.related_company_id,
                      t.related_project_id,t.source_chat_id,t.source_item_id,i.source_message_id,t.confidence,t.created_at,t.updated_at
               FROM tasks AS t LEFT JOIN ai_items AS i ON i.item_id=t.source_item_id WHERE t.task_id=?""",
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Task {task_id} was not found.")
        columns = (
            "task_id",
            "title",
            "details",
            "status",
            "owner",
            "due_date",
            "related_person_id",
            "related_company_id",
            "related_project_id",
            "source_chat_id",
            "source_item_id",
            "source_message_id",
            "confidence",
            "created_at",
            "updated_at",
        )
        return dict(zip(columns, row, strict=True))

    def _save_session(
        self,
        task_id: int,
        concepts: list[str],
        evidence: list[EvidenceItem],
        *,
        query: str | None,
        mode: str,
        as_of: str,
        diagnostics: dict,
        previous_session: int | None = None,
    ) -> int:
        now = utc_now()
        payload = json.dumps(
            {
                "concepts": concepts,
                "evidence_ids": [item.evidence_id for item in evidence],
            },
            sort_keys=True,
        )
        if previous_session:
            self.conn.execute(
                """UPDATE task_deep_dive_sessions SET summary_json=?,query_text=?,mode=?,as_of=?,
                   retrieval_version=1,diagnostics_json=?,updated_at=? WHERE session_id=?""",
                (
                    payload,
                    query,
                    mode,
                    as_of,
                    json.dumps(diagnostics, sort_keys=True),
                    now,
                    previous_session,
                ),
            )
            session_id = previous_session
        else:
            cursor = self.conn.execute(
                """INSERT INTO task_deep_dive_sessions(
                   task_id,summary_json,query_text,mode,as_of,retrieval_version,diagnostics_json,started_at,updated_at
                   ) VALUES (?,?,?,?,?,1,?,?,?)""",
                (
                    task_id,
                    payload,
                    query,
                    mode,
                    as_of,
                    json.dumps(diagnostics, sort_keys=True),
                    now,
                    now,
                ),
            )
            assert cursor.lastrowid is not None
            session_id = int(cursor.lastrowid)
        self.conn.execute(
            "DELETE FROM task_deep_dive_evidence WHERE session_id=?", (session_id,)
        )
        self.conn.executemany(
            "INSERT OR REPLACE INTO task_deep_dive_evidence(session_id,evidence_type,evidence_id,relevance_score,discovered_at) VALUES (?,?,?,?,?)",
            [
                (
                    session_id,
                    item.evidence_type,
                    item.evidence_id,
                    item.relevance_score,
                    now,
                )
                for item in evidence
            ],
        )
        self.conn.commit()
        return session_id

    def _report(
        self,
        task: dict,
        context,
        concepts: list[str],
        evidence: list[EvidenceItem],
        session_id: int,
        as_of: str,
        diagnostics: dict,
    ) -> TaskDeepDiveReport:
        notes = [
            dict(
                zip(
                    ("note_id", "content", "created_at", "updated_at"),
                    row,
                    strict=True,
                )
            )
            for row in self.conn.execute(
                "SELECT note_id,content,created_at,updated_at FROM task_notes WHERE task_id=? ORDER BY updated_at DESC",
                (task["task_id"],),
            )
        ]
        pins = {
            str(row[0])
            for row in self.conn.execute(
                "SELECT evidence_id FROM task_deep_dive_pins WHERE task_id=?",
                (task["task_id"],),
            )
        }
        fact_lines = [
            f"{item.get('predicate')}: {item.get('value')}" for item in context.facts
        ]
        origin = [f"Task was created at {task['created_at']}."]
        if task.get("source_chat_id") is not None:
            origin.append(
                f"Origin chat: {task['source_chat_id']}; source AI item: {task.get('source_item_id') or 'unknown'}."
            )
        source = self._source_item(task)
        if source:
            origin.append(
                f"Source item points to chat {source[0]} / message {source[1]} "
                f"at {source[2] or 'unknown time'}."
            )
        unknowns = []
        if not evidence:
            unknowns.append(
                "No source-backed evidence was found beyond the canonical task record."
            )
        if task["status"] in {"open", "waiting"} and not task.get("due_date"):
            unknowns.append("No due date is recorded for this open task.")
        loops = [
            f"{item['title']} ({item['status']})"
            for item in context.tasks
            if item.get("status") in {"open", "waiting"}
        ]
        recommendations = (
            ["Confirm the missing due date before treating timing as committed."]
            if task["status"] in {"open", "waiting"} and not task.get("due_date")
            else []
        )
        summary = f"{task['status'].capitalize()} task: {task['title']}. {len(evidence)} source-backed evidence item(s) were selected."
        timeline = sorted(
            evidence, key=lambda item: (item.occurred_at or "", item.evidence_id)
        )
        diagnostics.update(
            {
                "selected_evidence": len(evidence),
                "context_score": context.context_score,
                "session_id": session_id,
            }
        )
        return TaskDeepDiveReport(
            task,
            session_id,
            as_of,
            concepts,
            summary,
            origin,
            [
                f"Status: {task['status']}",
                f"Owner: {task['owner']}",
                f"Due: {task.get('due_date') or 'unknown'}",
            ],
            context.people,
            context.projects,
            context.companies,
            fact_lines,
            unknowns,
            loops,
            recommendations,
            timeline,
            evidence,
            notes,
            pins,
            diagnostics,
        )

    def _dedupe_and_limit(self, evidence: list[EvidenceItem]) -> list[EvidenceItem]:
        unique: dict[str, EvidenceItem] = {}
        for item in evidence:
            existing = unique.get(item.evidence_id)
            if existing is None:
                unique[item.evidence_id] = item
                continue
            winner, loser = (
                (item, existing)
                if item.relevance_score > existing.relevance_score
                else (existing, item)
            )
            winner.reasons = list(dict.fromkeys([*winner.reasons, *loser.reasons]))
            if not winner.conversation_window:
                winner.conversation_window = loser.conversation_window
            unique[item.evidence_id] = winner
        selected: list[EvidenceItem] = []
        chars = 0
        for item in sorted(
            unique.values(), key=lambda item: (-item.relevance_score, item.evidence_id)
        ):
            item_chars = len(item.title) + len(item.text)
            if (
                len(selected) >= self.settings.task_deep_dive_max_evidence
                or chars + item_chars > self.settings.task_deep_dive_max_context_chars
            ):
                continue
            selected.append(item)
            chars += item_chars
        return selected

    def _iterative_raw_evidence(
        self,
        task: dict,
        context,
        concepts: list[str],
        as_of: str,
    ) -> tuple[list[EvidenceItem], list[str], dict]:
        """Expand a task investigation only when the previous round taught us.

        Expansion is evidence-derived and capped by the existing settings; it
        never turns a broad keyword match into task evidence because retrieval
        still requires a task anchor, source chat, or graph-related chat.
        """
        all_evidence: list[EvidenceItem] = []
        known_ids: set[str] = set()
        known_terms = list(concepts)
        diagnostics: dict[str, int] = {
            "rounds_completed": 0,
            "new_evidence": 0,
            "new_concepts": 0,
            "fts_queries": 0,
            "fallback_queries": 0,
            "raw_candidates": 0,
            "raw_rejected": 0,
        }
        active_terms = list(concepts)
        for round_number in range(
            1, self.settings.task_deep_dive_max_search_rounds + 1
        ):
            raw, round_diagnostics = raw_message_evidence(
                self.conn,
                task,
                context,
                active_terms,
                self.settings,
                as_of=as_of,
            )
            for key in (
                "fts_queries",
                "fallback_queries",
                "raw_candidates",
                "raw_rejected",
            ):
                diagnostics[key] += int(round_diagnostics[key])
            fresh = [item for item in raw if item.evidence_id not in known_ids]
            diagnostics["rounds_completed"] = round_number
            if not fresh:
                break
            all_evidence.extend(fresh)
            known_ids.update(item.evidence_id for item in fresh)
            discovered = self._evidence_terms(fresh, known_terms)
            diagnostics["new_evidence"] += len(fresh)
            diagnostics["new_concepts"] += len(discovered)
            if not discovered:
                break
            known_terms.extend(discovered)
            active_terms = [*discovered, *concepts][
                : self.settings.task_deep_dive_max_queries_per_round
            ]
        return all_evidence, known_terms, diagnostics

    @staticmethod
    def _evidence_terms(
        evidence: list[EvidenceItem], known_terms: list[str]
    ) -> list[str]:
        known = set(known_terms)
        candidates: list[str] = []
        for item in evidence:
            for term in re.findall(r"[\w][\w-]{2,}", item.text.casefold()):
                if term not in known and term not in {
                    "that",
                    "this",
                    "with",
                    "from",
                    "have",
                    "will",
                    "could",
                    "about",
                    "before",
                    "today",
                }:
                    candidates.append(term)
        return list(dict.fromkeys(candidates))[:8]

    def _context(self, task_id: int, query: str, as_of: datetime | None):
        settings = replace(
            self.settings,
            context_max_graph_depth=self.settings.task_deep_dive_max_graph_depth,
        )
        return ContextBuilder(self.conn, settings).build(
            ContextRequest(
                purpose="task_reconciliation",
                task_ids=[task_id],
                query=query,
                as_of=as_of,
            )
        )

    def _discovered_terms(self, task_id: int, as_of: str) -> list[str]:
        row = self.conn.execute(
            "SELECT summary_json FROM task_deep_dive_sessions WHERE task_id=? AND as_of<=? ORDER BY as_of DESC,session_id DESC LIMIT 1",
            (task_id, as_of),
        ).fetchone()
        if not row:
            return []
        try:
            return list(json.loads(row[0]).get("concepts", []))[
                : self.settings.task_deep_dive_max_queries_per_round
            ]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def _source_item(self, task: dict) -> tuple[int, int, str | None] | None:
        if task.get("source_item_id") is None:
            return None
        row = self.conn.execute(
            "SELECT source_chat_id,source_message_id,source_date FROM ai_items WHERE item_id=?",
            (task["source_item_id"],),
        ).fetchone()
        if row is None:
            return None
        return int(row[0]), int(row[1]), row[2]

    def _origin_evidence(self, task: dict, as_of: str) -> list[EvidenceItem]:
        source = self._source_item(task)
        if source is None:
            return []
        chat_id, message_id, _ = source
        record = TelegramEvidenceSource(self.conn).get(str(chat_id), str(message_id))
        if (
            record is None
            or record.is_deleted
            or (record.occurred_at is not None and record.occurred_at > as_of)
        ):
            return []
        return [
            EvidenceItem(
                f"E-message-{chat_id}-{message_id}",
                "message",
                str(record.metadata.get("chat_title") or f"Chat {chat_id}"),
                str(record.content or ""),
                record.occurred_at,
                chat_id,
                message_id,
                100.0,
                None,
                ["task origin source message"],
            )
        ]
