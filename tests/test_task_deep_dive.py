from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from alex_memory.context.repository import ensure_relationship, set_temporal_fact
from alex_memory.database import connect
from alex_memory.operational import EntityResolver, normalize_task_title
from alex_memory.tasks.deep_dive import TaskDeepDiveService
from alex_memory.tasks.deep_dive.models import EvidenceItem
from alex_memory.tasks.deep_dive.retrieval import raw_message_evidence, task_concepts
from test_ai_pipeline import make_settings


class TaskDeepDiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(
            Path(self.directory.name), task_deep_dive_max_raw_messages=20
        )
        self.conn = connect(self.settings)
        self.now = "2026-08-22T12:00:00+00:00"
        resolver = EntityResolver(self.conn)
        self.michael = resolver.person("Michael", source="manual")
        self.george = resolver.person("George", source="manual")
        self.project = resolver.entity("project", "Georgia LP", source="manual")
        self.tbc = resolver.entity("company", "TBC", source="manual")
        assert self.michael and self.george and self.project and self.tbc
        ensure_relationship(
            self.conn,
            "person",
            self.michael,
            "project",
            self.project,
            "involved_in",
            1.0,
            100,
            1,
        )
        ensure_relationship(
            self.conn,
            "person",
            self.george,
            "project",
            self.project,
            "involved_in",
            1.0,
            200,
            1,
        )
        ensure_relationship(
            self.conn,
            "project",
            self.project,
            "company",
            self.tbc,
            "uses_bank",
            1.0,
            100,
            1,
        )
        cursor = self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,
               related_company_id,related_project_id,source_chat_id,confidence,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "Resolve TBC hedge pricing",
                normalize_task_title("Resolve TBC hedge pricing"),
                "Confirm the FX hedge difference for Georgia LP.",
                "open",
                "me",
                self.michael,
                self.tbc,
                self.project,
                100,
                1.0,
                self.now,
                self.now,
            ),
        )
        self.task_id = int(cursor.lastrowid)
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media,is_deleted) VALUES (?,?,?,?,0,0,0)",
            [
                (
                    100,
                    1,
                    "2026-08-20T10:00:00+00:00",
                    "Michael asked TBC for indicative hedge pricing for Georgia LP.",
                ),
                (
                    200,
                    1,
                    "2026-08-21T10:00:00+00:00",
                    "TBC spread is high; we could hedge the FX difference for Georgia LP.",
                ),
                (
                    200,
                    2,
                    "2026-08-21T10:01:00+00:00",
                    "George will compare the forward rate before replying.",
                ),
                (
                    300,
                    1,
                    "2026-08-21T11:00:00+00:00",
                    "I hedged my personal investment today.",
                ),
                (
                    100,
                    2,
                    "2026-08-23T10:00:00+00:00",
                    "TBC confirmed the final hedge price.",
                ),
            ],
        )
        self.conn.execute(
            """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,
               project_id,source_chat_id,source_message_id,confidence,created_at)
               VALUES ('pricing_discussion','TBC hedge discussion',?, ?, ?, ?, ?, ?, .9, ?)""",
            (
                "George raised the TBC hedge difference.",
                "2026-08-21T10:00:00+00:00",
                self.now,
                self.project,
                200,
                1,
                self.now,
            ),
        )
        self.conn.commit()
        self.service = TaskDeepDiveService(self.conn, self.settings)

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_cross_chat_evidence_is_bounded_and_filters_unrelated_messages(
        self,
    ) -> None:
        report = self.service.build(self.task_id)
        ids = {item.evidence_id for item in report.evidence}
        self.assertIn("E-message-100-1", ids)
        self.assertIn("E-message-200-1", ids)
        self.assertNotIn("E-message-300-1", ids)
        cross_chat = next(
            item for item in report.evidence if item.evidence_id == "E-message-200-1"
        )
        self.assertIn("task-linked anchor", " ".join(cross_chat.reasons))
        self.assertTrue(cross_chat.conversation_window)
        self.assertLessEqual(
            len(report.evidence), self.settings.task_deep_dive_max_evidence
        )
        self.assertGreater(report.session_id, 0)
        self.assertGreaterEqual(report.diagnostics["rounds_completed"], 1)
        self.assertLessEqual(
            report.diagnostics["rounds_completed"],
            self.settings.task_deep_dive_max_search_rounds,
        )
        self.assertEqual(
            "message",
            self.conn.execute(
                "SELECT evidence_type FROM task_deep_dive_evidence WHERE session_id=? AND evidence_id='E-message-200-1'",
                (report.session_id,),
            ).fetchone()[0],
        )

    def test_historical_deep_dive_fails_closed_and_notes_and_pins_persist(self) -> None:
        with self.assertRaisesRegex(ValueError, "Historical Task Deep Dive"):
            self.service.build(
                self.task_id, as_of=datetime.fromisoformat("2026-08-22T12:00:00+00:00")
            )
        note_id = self.service.add_note(
            self.task_id, "Ask Michael for the rate comparison."
        )
        self.service.build(self.task_id)
        self.service.pin_evidence(self.task_id, "E-message-200-1")
        refreshed = self.service.build(self.task_id)
        self.assertEqual(note_id, refreshed.notes[0]["note_id"])
        self.assertIn("E-message-200-1", refreshed.pinned_evidence_ids)

    def test_pin_rejects_evidence_outside_task_sessions(self) -> None:
        self.service.build(self.task_id)
        with self.assertRaisesRegex(ValueError, "investigation session"):
            self.service.pin_evidence(self.task_id, "E-message-999-1")

    def test_question_answer_stays_grounded_in_selected_evidence(self) -> None:
        answer, sources = self.service.ask(
            self.task_id, "What did George say about the hedge difference?"
        )
        self.assertTrue(sources)
        self.assertIn("[E-", answer)
        self.assertNotIn("personal investment", answer)

    def test_raw_evidence_uses_like_only_when_fts5_is_unavailable(self) -> None:
        task = self.service._task(self.task_id)
        context = self.service._context(
            self.task_id, task["title"], datetime.fromisoformat(self.now)
        )
        concepts = ["hedge", "pricing"]
        with patch(
            "alex_memory.tasks.deep_dive.retrieval.fts5_available", return_value=False
        ):
            _, diagnostics = raw_message_evidence(
                self.conn,
                task,
                context,
                concepts,
                self.settings,
                as_of=self.now,
            )
        self.assertEqual(0, diagnostics["fts_queries"])
        self.assertEqual(2, diagnostics["fallback_queries"])

    def test_broken_fts_query_is_surfaced(self) -> None:
        task = self.service._task(self.task_id)
        context = self.service._context(
            self.task_id, task["title"], datetime.fromisoformat(self.now)
        )
        self.conn.execute("DROP TABLE messages_fts")
        with self.assertRaises(sqlite3.OperationalError):
            raw_message_evidence(
                self.conn,
                task,
                context,
                ["hedge"],
                self.settings,
                as_of=self.now,
            )

    def test_contextual_fact_and_unlinked_event_are_not_task_evidence(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="project",
            subject_id=self.project,
            predicate="project_status",
            value={"status": "active"},
            valid_from=self.now,
            confidence=0.9,
        )
        event_id = self.conn.execute(
            """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,
                   project_id,confidence,created_at)
               VALUES ('project_updated','Unrelated project update','No task link',?,?,?,0.9,?)""",
            (self.now, self.now, self.project, self.now),
        ).lastrowid

        report = self.service.build(self.task_id)

        ids = {item.evidence_id for item in report.evidence}
        self.assertNotIn(f"E-event-{event_id}", ids)
        self.assertFalse(any(item.evidence_type == "fact" for item in report.evidence))
        self.assertTrue(report.known_facts)

    def test_exact_task_event_is_evidence(self) -> None:
        event_id = self.conn.execute(
            """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,
                   task_id,confidence,created_at)
               VALUES ('task_updated','Task lifecycle','Task is waiting',?,?,?,0.9,?)""",
            (self.now, self.now, self.task_id, self.now),
        ).lastrowid

        report = self.service.build(self.task_id)

        linked = next(
            item
            for item in report.evidence
            if item.evidence_id == f"E-event-{event_id}"
        )
        self.assertIn("exact canonical task link", linked.reasons)

    def test_unicode_task_title_matches_linkless_event_conservatively(self) -> None:
        self.conn.execute(
            "UPDATE tasks SET title='Подтвердить цену хеджирования' WHERE task_id=?",
            (self.task_id,),
        )
        event_id = self.conn.execute(
            """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,
                   project_id,confidence,created_at)
               VALUES ('pricing_discussion','Цена хеджирования','Подтвердить цену',?,?,?,0.9,?)""",
            (self.now, self.now, self.project, self.now),
        ).lastrowid

        report = self.service.build(self.task_id)

        matched = next(
            item
            for item in report.evidence
            if item.evidence_id == f"E-event-{event_id}"
        )
        self.assertIn("conservative task-title match", matched.reasons)

    def test_dedupe_retains_strongest_provenance_and_reasons(self) -> None:
        weak = EvidenceItem(
            "E-message-100-1",
            "message",
            "Raw",
            "weak copy",
            relevance_score=10,
            reasons=["raw task-linked anchor"],
        )
        origin = EvidenceItem(
            "E-message-100-1",
            "message",
            "Origin",
            "exact origin",
            relevance_score=100,
            reasons=["task origin source message"],
        )

        selected = self.service._dedupe_and_limit([weak, origin])

        self.assertEqual(["exact origin"], [item.text for item in selected])
        self.assertEqual(
            {"raw task-linked anchor", "task origin source message"},
            set(selected[0].reasons),
        )

    def test_report_evidence_has_explicit_membership_reason(self) -> None:
        report = self.service.build(self.task_id)
        self.assertTrue(report.evidence)
        self.assertTrue(all(item.reasons for item in report.evidence))

    def test_multilingual_concepts_do_not_need_deal_specific_expansion(self) -> None:
        task = self.service._task(self.task_id)
        task["title"] = "Подтвердить ქართული პირობები"
        context = self.service._context(self.task_id, task["title"], None)

        concepts = task_concepts(task, context)
        discovered = self.service._evidence_terms(
            [EvidenceItem("E-test", "message", "test", "ქართული პასუხი")], concepts
        )

        self.assertIn("подтвердить", concepts)
        self.assertIn("ქართული", concepts)
        self.assertIn("პასუხი", discovered)
