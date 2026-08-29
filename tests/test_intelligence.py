from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from alex_memory.database import connect
from alex_memory.context.repository import set_temporal_fact
from alex_memory.intelligence import (
    answer_question,
    answer_question_with_ai,
    attention_items,
    evaluate_follow_ups,
    evaluate_project_health,
    manually_update_follow_up,
    profile,
    reject_task,
    refresh_operational_state,
    retrieve,
    set_chat_policy,
    select_evidence,
    validate_citations,
)
from alex_memory.ai.providers.base import ProviderError
from alex_memory.retrieval import SearchResult
from alex_memory.intelligence import _notify
from alex_memory.retrieval import _entity_hints, retrieve_related
from alex_memory.schema_support import fts5_available, fts_index_health
from alex_memory.operational import _merge_entities

from test_ai_pipeline import make_settings


class IntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        now = "2026-08-21T12:00:00+00:00"
        self.person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Michael',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO entity_aliases(entity_type,entity_id,alias,normalized_alias,created_at) VALUES ('person',?,'Michael','michael',?)",
            (self.person_id, now),
        )
        self.project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Georgia LP',?,?)",
            (now, now),
        ).lastrowid
        self.task_id = self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,related_project_id,source_chat_id,due_date,confidence,created_at,updated_at)
               VALUES ('Corporate documents','corporate documents','Michael said he is still waiting internally.','waiting','other',?,?,100,'2026-08-19',1.0,?,?)""",
            (self.person_id, self.project_id, now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,82411,'2026-08-21T12:00:00+00:00','Michael says he is still waiting internally on corporate documents.',0,0)"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_user_facing_chat_policy_labels_map_to_enforceable_modes(self) -> None:
        aliases = {
            "full": "include",
            "archive_only": "classify_only",
            "news_only": "news_only",
            "ignore": "exclude",
        }
        for mode, stored_mode in aliases.items():
            set_chat_policy(self.conn, 100, mode)
            self.assertEqual(
                stored_mode,
                self.conn.execute(
                    "SELECT mode FROM chat_ai_policy WHERE chat_id=100"
                ).fetchone()[0],
            )

    def test_ask_is_grounded_and_cited(self) -> None:
        answer, sources = answer_question(
            self.conn, "What am I waiting for from Michael?", self.settings
        )
        self.assertIn("Corporate documents", answer)
        self.assertIn("Task #", answer)
        self.assertTrue(sources)
        self.assertTrue(validate_citations(answer, len(sources)))

    def test_ask_routes_model_answer_and_keeps_deterministic_fallback(self) -> None:
        class AnswerRouter:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            async def answer(self, prompt: str) -> str:
                self.prompts.append(prompt)
                return "Corporate documents are still waiting. [1]"

        router = AnswerRouter()
        answer, sources = asyncio.run(
            answer_question_with_ai(
                self.conn,
                "What am I waiting for from Michael?",
                self.settings,
                router=router,
            )
        )
        self.assertEqual("Corporate documents are still waiting. [1]", answer)
        self.assertTrue(sources)
        self.assertEqual(1, len(router.prompts))

    def test_ask_falls_back_only_for_typed_provider_failure(self) -> None:
        class OfflineRouter:
            async def answer(self, prompt: str) -> str:
                raise ProviderError("offline")

        fallback, _ = answer_question(
            self.conn, "What am I waiting for from Michael?", self.settings
        )
        answer, _ = asyncio.run(
            answer_question_with_ai(
                self.conn,
                "What am I waiting for from Michael?",
                self.settings,
                router=OfflineRouter(),
            )
        )
        self.assertEqual(fallback, answer)

    def test_ask_does_not_hide_unexpected_router_failure(self) -> None:
        class BrokenRouter:
            async def answer(self, prompt: str) -> str:
                raise ValueError("broken local wiring")

        with self.assertRaisesRegex(ValueError, "broken local wiring"):
            asyncio.run(
                answer_question_with_ai(
                    self.conn,
                    "What am I waiting for from Michael?",
                    self.settings,
                    router=BrokenRouter(),
                )
            )

    def test_evidence_selection_keeps_a_mixed_bounded_set(self) -> None:
        rows = [
            SearchResult("task", "Waiting task", "WAITING — approval", None, 100),
            SearchResult("fact", "document_status", "received", None, 99),
            SearchResult("summary", "Daily summary", "Terms discussed", None, 98),
            SearchResult("message", "Telegram", "Contract terms", None, 97),
        ]

        selected = select_evidence(
            rows, "What is the contract status?", self.settings, max_items=4
        )

        self.assertEqual(
            {"task", "fact", "summary", "message"},
            {row.result_type for row in selected},
        )

    def test_search_and_crm_profile_share_canonical_person(self) -> None:
        rows = retrieve(self.conn, "Michael corporate documents", self.settings)
        self.assertTrue(any(row.task_id == self.task_id for row in rows))
        data = profile(self.conn, "person", self.person_id)
        self.assertEqual("Michael", data["entity"][1])
        self.assertEqual(self.task_id, data["tasks"][0]["task_id"])

    def test_sql_fallback_matches_query_terms_independent_of_word_order(self) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (100,82412,'2026-08-21T12:01:00+00:00',
                       'Contract need remains pending with legal.',0,0)"""
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (100,82413,'2026-08-21T12:02:00+00:00',
                       'Contract approval remains pending with legal.',0,0)"""
        )
        self.conn.commit()

        with patch("alex_memory.retrieval.fts5_available", return_value=False):
            forward = retrieve(self.conn, "contract need", self.settings)
            reverse = retrieve(self.conn, "need contract", self.settings)

        for rows in (forward, reverse):
            self.assertIn(82412, [row.message_id for row in rows])
            self.assertNotIn(82413, [row.message_id for row in rows])

        if fts5_available(self.conn):
            fts_rows = retrieve(self.conn, "need contract", self.settings)
            self.assertIn(82412, [row.message_id for row in fts_rows])
            self.assertNotIn(82413, [row.message_id for row in fts_rows])

    def test_related_retrieval_uses_canonical_links_not_name_search(self) -> None:
        other = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('George',?,?)",
            ("2026-08-21T12:00:00+00:00",) * 2,
        ).lastrowid
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,
               confidence,created_at,updated_at) VALUES ('Michael name only','michael name only',
               'Mentions Michael but belongs to George.','open','other',?,1,?,?)""",
            (other, "2026-08-21T12:00:00+00:00", "2026-08-21T12:00:00+00:00"),
        )
        self.conn.commit()
        rows = retrieve_related(self.conn, "person", self.person_id, self.settings)
        self.assertEqual([self.task_id], [row.task_id for row in rows if row.task_id])

    def test_related_retrieval_uses_observation_not_legacy_wrapper(self) -> None:
        self.conn.execute(
            """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
               source_chat_id,source_message_id,source_date,person_id,created_at,dedupe_key)
               VALUES (1,'note','Michael prefers email','Use email for updates.',
                       'informational','unknown',0.9,100,1,'2026-08-21T12:00:00+00:00',?,'now',
                       'michael-prefers-email')""",
            (self.person_id,),
        )
        self.conn.execute(
            """INSERT INTO context_events(event_type,title,description,occurred_at,observed_at,
               person_id,source_ai_item_id,confidence,created_at)
               VALUES ('observation_recorded','Michael prefers email','Use email for updates.',
                       '2026-08-21T12:00:00+00:00','2026-08-21T12:00:00+00:00',?,1,0.9,'now')""",
            (self.person_id,),
        )
        self.conn.commit()

        rows = retrieve_related(self.conn, "person", self.person_id, self.settings)

        observations = [row for row in rows if row.result_type == "observation"]
        self.assertEqual(["Michael prefers email"], [row.title for row in observations])
        self.assertNotIn("event", [row.result_type for row in rows])

    def test_related_retrieval_supports_each_canonical_scope(self) -> None:
        now = "2026-08-21T12:00:00+00:00"
        company_id = self.conn.execute(
            "INSERT INTO companies(canonical_name,created_at,updated_at) VALUES ('Legal Co',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "UPDATE tasks SET related_company_id=? WHERE task_id=?",
            (company_id, self.task_id),
        )
        self.conn.commit()

        for entity_type, entity_id in (
            ("person", self.person_id),
            ("company", company_id),
            ("project", self.project_id),
            ("task", self.task_id),
        ):
            rows = retrieve_related(self.conn, entity_type, entity_id, self.settings)
            self.assertEqual(
                [self.task_id], [row.task_id for row in rows if row.task_id]
            )

    def test_retrieval_keeps_distinct_daily_summary_provenance(self) -> None:
        self.conn.executemany(
            "INSERT INTO chat_daily_summaries(chat_id,summary_date,summary,chunk_count,updated_at) VALUES (100,?,?,1,?)",
            [
                ("2026-08-20", "Need contract review", "2026-08-20T12:00:00+00:00"),
                ("2026-08-21", "Need contract approval", "2026-08-21T12:00:00+00:00"),
            ],
        )
        self.conn.commit()

        rows = retrieve(self.conn, "Need contract", self.settings)

        self.assertEqual(
            ["2026-08-21", "2026-08-20"],
            [row.date for row in rows if row.result_type == "summary"],
        )

    def test_related_retrieval_as_of_excludes_future_task_and_uses_fact_interval(
        self,
    ) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="document_status",
            value={"status": "requested"},
            valid_from="2026-08-19T10:00:00+00:00",
            confidence=0.9,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="document_status",
            value={"status": "received"},
            valid_from="2026-08-22T10:00:00+00:00",
            confidence=0.9,
            conflict_policy="replace",
        )
        self.conn.commit()

        rows = retrieve_related(
            self.conn,
            "person",
            self.person_id,
            self.settings,
            as_of="2026-08-20T12:00:00+00:00",
        )

        self.assertNotIn(self.task_id, [row.task_id for row in rows])
        facts = [row for row in rows if row.result_type == "fact"]
        self.assertEqual(['{"status": "requested"}'], [row.snippet for row in facts])

    def test_search_boosts_message_in_matching_project_segment(self) -> None:
        now = "2026-08-21T12:00:00+00:00"
        self.conn.execute(
            """INSERT INTO entity_aliases(
                   entity_type,entity_id,alias,normalized_alias,created_at
               ) VALUES ('project',?,'Georgia LP','georgia lp',?)""",
            (self.project_id, now),
        )
        self.conn.execute(
            """INSERT INTO conversation_segments(
                   chat_id,project_id,started_at,ended_at,anchor_count,confidence,
                   source,created_at,updated_at
               ) VALUES (100,?,'2026-08-01','2026-09-01',2,0.95,'task_anchors',?,?)""",
            (self.project_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (100,82412,?,'Segmented hedge evidence for Georgia LP.',0,0)""",
            (now,),
        )
        self.conn.commit()

        rows = retrieve(self.conn, "Georgia LP segmented hedge evidence", self.settings)
        result = next(row for row in rows if row.message_id == 82412)
        self.assertGreaterEqual(result.score, 76)

    def test_entity_hints_are_sql_filtered_and_bounded(self) -> None:
        now = "2026-08-21T12:00:00+00:00"
        self.conn.executemany(
            """INSERT INTO entity_aliases(entity_type,entity_id,alias,normalized_alias,created_at)
               VALUES ('person',? ,?,?,?)""",
            [
                (self.person_id, f"Unused {number}", f"unused{number}", now)
                for number in range(60)
            ],
        )
        statements: list[str] = []
        self.conn.set_trace_callback(statements.append)
        people, companies, projects = _entity_hints(self.conn, "michael documents")
        self.conn.set_trace_callback(None)

        self.assertEqual([self.person_id], people)
        self.assertEqual([-1], companies)
        self.assertEqual([-1], projects)
        self.assertTrue(
            any(
                "instr(" in statement and "LIMIT 48" in statement
                for statement in statements
            )
        )

    def test_follow_up_is_deduplicated(self) -> None:
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, date(2026, 8, 25))
        )
        self.assertEqual(
            0, evaluate_follow_ups(self.conn, self.settings, date(2026, 8, 25))
        )
        self.assertEqual(
            1, self.conn.execute("SELECT COUNT(*) FROM follow_ups").fetchone()[0]
        )

    def test_follow_up_reconciles_automatic_state_and_preserves_manual_state(
        self,
    ) -> None:
        evaluation_day = date(2026, 8, 25)
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        follow_up_id = self.conn.execute(
            "SELECT follow_up_id FROM follow_ups"
        ).fetchone()[0]

        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE task_id=?", (self.task_id,)
        )
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        self.assertEqual(
            "cancelled",
            self.conn.execute(
                "SELECT status FROM follow_ups WHERE follow_up_id=?", (follow_up_id,)
            ).fetchone()[0],
        )

        self.conn.execute(
            "UPDATE tasks SET status='waiting',updated_at=? WHERE task_id=?",
            ("2026-08-20T12:00:00+00:00", self.task_id),
        )
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        self.assertEqual(
            ("open", None),
            self.conn.execute(
                "SELECT status,resolved_at FROM follow_ups WHERE follow_up_id=?",
                (follow_up_id,),
            ).fetchone(),
        )

        self.conn.execute(
            "UPDATE tasks SET updated_at=? WHERE task_id=?",
            ("2026-08-25T12:00:00+00:00", self.task_id),
        )
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        self.assertEqual(
            "cancelled",
            self.conn.execute(
                "SELECT status FROM follow_ups WHERE follow_up_id=?", (follow_up_id,)
            ).fetchone()[0],
        )
        self.conn.execute(
            "UPDATE tasks SET updated_at=? WHERE task_id=?",
            ("2026-08-20T12:00:00+00:00", self.task_id),
        )
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        self.assertTrue(manually_update_follow_up(self.conn, follow_up_id, "snoozed"))
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE task_id=?", (self.task_id,)
        )
        self.assertEqual(
            0, evaluate_follow_ups(self.conn, self.settings, evaluation_day)
        )
        self.assertEqual(
            "snoozed",
            self.conn.execute(
                "SELECT status FROM follow_ups WHERE follow_up_id=?", (follow_up_id,)
            ).fetchone()[0],
        )

    def test_manual_follow_up_state_is_audited_and_can_be_reopened(self) -> None:
        self.assertEqual(
            1, evaluate_follow_ups(self.conn, self.settings, date(2026, 8, 25))
        )
        follow_up_id = self.conn.execute(
            "SELECT follow_up_id FROM follow_ups"
        ).fetchone()[0]

        self.assertTrue(manually_update_follow_up(self.conn, follow_up_id, "done"))
        status, resolved_at = self.conn.execute(
            "SELECT status,resolved_at FROM follow_ups WHERE follow_up_id=?",
            (follow_up_id,),
        ).fetchone()
        self.assertEqual("done", status)
        self.assertIsNotNone(resolved_at)
        feedback = self.conn.execute(
            """SELECT feedback_type,payload_json FROM user_feedback
               WHERE entity_type='follow_up' AND entity_id=?""",
            (follow_up_id,),
        ).fetchone()
        self.assertEqual("manual_follow_up_status", feedback[0])
        self.assertEqual(
            {"previous_status": "open", "status": "done"}, json.loads(feedback[1])
        )
        self.assertTrue(manually_update_follow_up(self.conn, follow_up_id, "done"))
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM user_feedback WHERE entity_type='follow_up'"
            ).fetchone()[0],
        )

        self.assertTrue(manually_update_follow_up(self.conn, follow_up_id, "open"))
        self.assertEqual(
            ("open", None),
            self.conn.execute(
                "SELECT status,resolved_at FROM follow_ups WHERE follow_up_id=?",
                (follow_up_id,),
            ).fetchone(),
        )
        self.assertFalse(manually_update_follow_up(self.conn, 999, "done"))
        with self.assertRaises(ValueError):
            manually_update_follow_up(self.conn, follow_up_id, "invalid")

    def test_attention_is_read_only_and_refresh_is_explicit_and_idempotent(
        self,
    ) -> None:
        before = self.conn.total_changes
        rows = attention_items(self.conn, self.settings)
        self.assertTrue(rows)
        self.assertEqual(before, self.conn.total_changes)
        self.assertEqual(
            (1, 1),
            refresh_operational_state(self.conn, self.settings, date(2026, 8, 25)),
        )
        self.assertEqual(
            (0, 0),
            refresh_operational_state(self.conn, self.settings, date(2026, 8, 25)),
        )
        follow_up = next(
            row
            for row in attention_items(self.conn, self.settings)
            if row.result_type == "follow-up"
        )
        self.assertEqual(self.task_id, follow_up.task_id)

    def test_notification_cooldown_uses_elapsed_time_not_calendar_buckets(self) -> None:
        from datetime import UTC, datetime

        class Clock(datetime):
            current = datetime(2026, 8, 24, 23, 59, tzinfo=UTC)

            @classmethod
            def now(cls, tz=None):
                return (
                    cls.current.astimezone(tz)
                    if tz
                    else cls.current.replace(tzinfo=None)
                )

        with patch("alex_memory.intelligence.datetime", Clock):
            _notify(
                self.conn,
                self.settings,
                "project_stale",
                "high",
                "Project stale",
                "No recent activity.",
                "project",
                self.project_id,
                "project-stale:1",
            )
            Clock.current = datetime(2026, 8, 25, 0, 1, tzinfo=UTC)
            _notify(
                self.conn,
                self.settings,
                "project_stale",
                "high",
                "Project stale",
                "No recent activity.",
                "project",
                self.project_id,
                "project-stale:1",
            )
            Clock.current = datetime(2026, 8, 25, 23, 59, 1, tzinfo=UTC)
            _notify(
                self.conn,
                self.settings,
                "project_stale",
                "high",
                "Project stale",
                "No recent activity.",
                "project",
                self.project_id,
                "project-stale:1",
            )
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM notification_outbox WHERE event_type='project_stale'"
            ).fetchone()[0],
        )

    def test_stale_project_creates_notification(self) -> None:
        self.conn.execute(
            "UPDATE tasks SET due_date=NULL,related_project_id=NULL WHERE task_id=?",
            (self.task_id,),
        )
        evaluate_project_health(self.conn, self.settings, date(2026, 9, 5))
        self.assertEqual(
            "stale",
            self.conn.execute(
                "SELECT status FROM projects WHERE project_id=?", (self.project_id,)
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM notification_outbox WHERE event_type='project_stale'"
            ).fetchone()[0],
        )

    def test_recent_project_evidence_is_active_without_task_link(self) -> None:
        self.conn.execute(
            "UPDATE tasks SET due_date=NULL,related_project_id=NULL WHERE task_id=?",
            (self.task_id,),
        )
        self.conn.execute(
            """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
               source_chat_id,source_message_id,source_date,project_id,created_at,dedupe_key)
               VALUES (1,'project','Georgia LP','','informational','unknown',0.96,
               100,1,'2026-09-04T12:00:00+00:00',?,'now','recent-project-evidence')""",
            (self.project_id,),
        )

        evaluate_project_health(self.conn, self.settings, date(2026, 9, 5))

        self.assertEqual(
            "active",
            self.conn.execute(
                "SELECT status FROM projects WHERE project_id=?", (self.project_id,)
            ).fetchone()[0],
        )

    def test_real_overdue_project_task_is_critical(self) -> None:
        evaluate_project_health(self.conn, self.settings, date(2026, 9, 5))

        self.assertEqual(
            "critical",
            self.conn.execute(
                "SELECT status FROM projects WHERE project_id=?", (self.project_id,)
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM notification_outbox WHERE event_type='project_critical'"
            ).fetchone()[0],
        )

    def test_manual_rejection_locks_task(self) -> None:
        self.assertTrue(reject_task(self.conn, self.task_id))
        self.assertTrue(reject_task(self.conn, self.task_id))
        self.assertEqual(
            ("canceled", 1),
            self.conn.execute(
                "SELECT status,manual_status_locked FROM tasks WHERE task_id=?",
                (self.task_id,),
            ).fetchone(),
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM user_feedback WHERE feedback_type='reject_task'"
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                """SELECT COUNT(*) FROM task_events
                   WHERE task_id=? AND event_type='manual_update'""",
                (self.task_id,),
            ).fetchone()[0],
        )

    def test_invalid_citation_is_rejected(self) -> None:
        self.assertFalse(validate_citations("Unsupported [999]", 2))

    def test_fts_tracks_source_mutations_and_entity_merge(self) -> None:
        if not fts5_available(self.conn):
            self.skipTest("SQLite was built without optional FTS5")
        self.conn.execute(
            "UPDATE messages SET text='Michael supplied revised documents.' WHERE chat_id=100 AND message_id=82411"
        )
        self.assertEqual(
            ("Michael supplied revised documents.",),
            self.conn.execute(
                "SELECT text FROM messages_fts WHERE chat_id=100 AND message_id=82411"
            ).fetchone(),
        )
        self.conn.execute(
            "UPDATE messages SET is_deleted=1 WHERE chat_id=100 AND message_id=82411"
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM messages_fts WHERE chat_id=100 AND message_id=82411"
            ).fetchone()
        )
        duplicate = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Mikhail',?,?)",
            ("2026-08-21T12:00:00+00:00", "2026-08-21T12:00:00+00:00"),
        ).lastrowid
        self.conn.execute(
            "UPDATE people SET canonical_name='Michael K.' WHERE person_id=?",
            (self.person_id,),
        )
        self.assertEqual(
            ("Michael K.",),
            self.conn.execute(
                "SELECT name FROM entities_fts WHERE entity_type='person' AND entity_id=?",
                (self.person_id,),
            ).fetchone(),
        )
        _merge_entities(self.conn, "person", self.person_id, [int(duplicate)])
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM entities_fts WHERE entity_type='person' AND entity_id=?",
                (duplicate,),
            ).fetchone()
        )
        self.assertTrue(fts_index_health(self.conn)["healthy"])

    def test_broken_present_fts_index_is_not_silently_ignored(self) -> None:
        if not fts5_available(self.conn):
            self.skipTest("SQLite was built without optional FTS5")
        self.conn.execute("DROP TABLE messages_fts")
        with self.assertRaises(sqlite3.OperationalError):
            retrieve(self.conn, "Michael corporate documents", self.settings)
