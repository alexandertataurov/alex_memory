from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from alex_memory.context import ConversationContextService
from alex_memory.context.repository import add_event
from alex_memory.database import connect
from alex_memory.intelligence import answer_question
from alex_memory.operational import EntityResolver, _merge_entities

from test_ai_pipeline import make_settings


class ConversationIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        now = "2026-06-01T09:00:00+00:00"
        resolver = EntityResolver(self.conn)
        self.person_id = resolver.person("Michael", source="manual")
        self.georgia = resolver.entity("project", "Georgia LP", source="manual")
        self.dubai = resolver.entity("project", "Dubai LP", source="manual")
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (10,'Michael','user')"
        )
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,?,?,?,?,0)""",
            [
                (1, "2026-06-01T09:00:00+00:00", "What rate can they give us?", 1),
                (2, "2026-06-03T09:00:00+00:00", "1.2% above benchmark.", 0),
                (3, "2026-08-20T09:00:00+00:00", "Can we proceed with Dubai?", 0),
            ],
        )
        self.conn.executemany(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,
                   related_project_id,source_chat_id,due_date,confidence,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    "Confirm TBC pricing",
                    "confirm tbc pricing",
                    "Rate remains unresolved.",
                    "waiting",
                    "other",
                    self.person_id,
                    self.georgia,
                    10,
                    None,
                    0.9,
                    now,
                    now,
                ),
                (
                    "Send Dubai documents",
                    "send dubai documents",
                    "Documents requested.",
                    "open",
                    "me",
                    self.person_id,
                    self.dubai,
                    10,
                    None,
                    0.9,
                    "2026-08-20T09:00:00+00:00",
                    "2026-08-20T09:00:00+00:00",
                ),
            ],
        )
        add_event(
            self.conn,
            event_type="project_updated",
            title="Georgia LP pricing discussed",
            description="Indicative rate remains unresolved.",
            occurred_at="2026-06-01T09:00:00+00:00",
            person_id=self.person_id,
            project_id=self.georgia,
            source_chat_id=10,
            source_message_id=1,
            confidence=0.9,
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_refresh_materializes_segments_context_and_question_answer_link(
        self,
    ) -> None:
        service = ConversationContextService(self.conn, self.settings)
        self.assertEqual(1, service.refresh_person(self.person_id))
        self.conn.commit()

        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM conversation_contact_segments WHERE person_id=?",
                (self.person_id,),
            ).fetchone()[0],
        )
        service.refresh_conversation(self.person_id, 10)
        self.assertEqual(
            2,
            self.conn.execute(
                """SELECT COUNT(*) FROM conversation_open_loops
                   WHERE person_id=? AND loop_type='task'""",
                (self.person_id,),
            ).fetchone()[0],
        )
        current = self.conn.execute(
            """SELECT current_state,topic_json FROM current_conversation_context
               WHERE person_id=? AND conversation_id='10'""",
            (self.person_id,),
        ).fetchone()
        self.assertIn("Send Dubai documents", current[0])
        self.assertIn("dubai", current[1])
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM conversation_context_links WHERE link_type='question_answer'"
            ).fetchone()[0],
        )
        self.assertEqual(
            2,
            self.conn.execute(
                "SELECT COUNT(*) FROM person_project_context WHERE person_id=?",
                (self.person_id,),
            ).fetchone()[0],
        )

    def test_refresh_version_tracks_semantic_content_not_refresh_count(self) -> None:
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_conversation(self.person_id, 10)
        first = self.conn.execute(
            """SELECT context_version,evidence_through_at
               FROM current_conversation_context
               WHERE person_id=? AND conversation_id='10'""",
            (self.person_id,),
        ).fetchone()
        service.refresh_conversation(self.person_id, 10)
        self.assertEqual(
            first,
            self.conn.execute(
                """SELECT context_version,evidence_through_at
                   FROM current_conversation_context
                   WHERE person_id=? AND conversation_id='10'""",
                (self.person_id,),
            ).fetchone(),
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,99,'2026-09-01T09:00:00+00:00','Archived later source.',0,0)"""
        )
        service.refresh_conversation(self.person_id, 10)
        self.assertEqual(
            (1, "2026-09-01T09:00:00+00:00"),
            self.conn.execute(
                """SELECT context_version,evidence_through_at
                   FROM current_conversation_context
                   WHERE person_id=? AND conversation_id='10'""",
                (self.person_id,),
            ).fetchone(),
        )

    def test_temporal_package_uses_the_matching_historical_period(self) -> None:
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_person(self.person_id)
        package = service.build_for_conversation(
            person_id=self.person_id,
            conversation_id=10,
            as_of=datetime(2026, 6, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(self.georgia, package["conversation"]["primary_project_id"])
        self.assertNotIn("Dubai", package["conversation"]["current_state"])
        self.assertTrue(package["context"].segments)
        self.assertEqual([], package["project_contexts"])

    def test_historical_package_fails_closed_outside_active_segment(self) -> None:
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_person(self.person_id)

        package = service.build_for_conversation(
            person_id=self.person_id,
            conversation_id=10,
            as_of=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

        self.assertIsNone(package["conversation"]["primary_project_id"])
        self.assertEqual([], package["project_contexts"])

    def test_refresh_removes_task_loops_after_done_or_canceled(self) -> None:
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_conversation(self.person_id, 10)
        self.assertEqual(
            2,
            self.conn.execute(
                """SELECT COUNT(*) FROM conversation_open_loops
                   WHERE person_id=? AND loop_type='task'""",
                (self.person_id,),
            ).fetchone()[0],
        )
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE title='Confirm TBC pricing'"
        )
        self.conn.execute(
            "UPDATE tasks SET status='canceled' WHERE title='Send Dubai documents'"
        )

        service.refresh_conversation(self.person_id, 10)

        self.assertEqual(
            0,
            self.conn.execute(
                """SELECT COUNT(*) FROM conversation_open_loops
                   WHERE person_id=? AND loop_type='task'""",
                (self.person_id,),
            ).fetchone()[0],
        )

    def test_refresh_removes_orphan_task_loop(self) -> None:
        now = "2026-08-20T09:00:00+00:00"
        self.conn.execute(
            """INSERT INTO conversation_open_loops(person_id,source_type,conversation_id,loop_type,
                   title,owner,status,task_id,source_chat_id,source_message_id,confidence,created_at,updated_at)
               VALUES (?,'telegram','10','task','Old derived loop','me','waiting',999,10,99,0.9,?,?)""",
            (self.person_id, now, now),
        )

        ConversationContextService(self.conn, self.settings).refresh_conversation(
            self.person_id, 10
        )

        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM conversation_open_loops WHERE task_id=999"
            ).fetchone()
        )

    def test_refresh_preserves_non_task_durable_loop(self) -> None:
        now = "2026-08-20T09:00:00+00:00"
        self.conn.execute(
            """INSERT INTO conversation_open_loops(person_id,source_type,conversation_id,loop_type,
                   title,owner,status,source_chat_id,source_message_id,confidence,created_at,updated_at)
               VALUES (?,'telegram','10','promise','Send signed terms','me','waiting',10,99,0.9,?,?)""",
            (self.person_id, now, now),
        )

        ConversationContextService(self.conn, self.settings).refresh_conversation(
            self.person_id, 10
        )

        self.assertEqual(
            "waiting",
            self.conn.execute(
                """SELECT status FROM conversation_open_loops
                   WHERE loop_type='promise' AND source_message_id=99"""
            ).fetchone()[0],
        )

    def test_weak_or_late_reply_does_not_resolve_question_loop(self) -> None:
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,?,?,?,?,0)""",
            [
                (
                    20,
                    "2026-08-21T09:00:00+00:00",
                    "Can we proceed with the documents?",
                    1,
                ),
                (21, "2026-08-21T09:01:00+00:00", "yes", 0),
                (
                    22,
                    "2026-08-21T09:02:00+00:00",
                    "The documents were sent to legal today.",
                    0,
                ),
            ],
        )

        ConversationContextService(self.conn, self.settings).refresh_conversation(
            self.person_id, 10
        )

        self.assertEqual(
            "waiting",
            self.conn.execute(
                """SELECT status FROM conversation_open_loops
                   WHERE loop_type='question' AND source_message_id=20"""
            ).fetchone()[0],
        )
        self.assertIsNone(
            self.conn.execute(
                """SELECT 1 FROM conversation_context_links
                   WHERE link_type='question_answer' AND from_message_id=20"""
            ).fetchone()
        )

    def test_old_question_loop_ages_out_of_current_state(self) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,30,'2025-01-01T09:00:00+00:00',
                       'Can we proceed with the documents?',1,0)"""
        )

        ConversationContextService(self.conn, self.settings).refresh_conversation(
            self.person_id, 10
        )

        self.assertEqual(
            "resolved",
            self.conn.execute(
                """SELECT status FROM conversation_open_loops
                   WHERE loop_type='question' AND source_message_id=30"""
            ).fetchone()[0],
        )

    def test_only_the_adjacent_question_gets_a_nearby_answer(self) -> None:
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,?,?,?,?,0)""",
            [
                (40, "2026-08-22T09:00:00+00:00", "Can we proceed with documents?", 1),
                (41, "2026-08-22T09:01:00+00:00", "What rate can they offer?", 1),
                (
                    42,
                    "2026-08-22T09:02:00+00:00",
                    "They can offer 1.2% above benchmark.",
                    0,
                ),
            ],
        )

        ConversationContextService(self.conn, self.settings).refresh_conversation(
            self.person_id, 10
        )

        states = dict(
            self.conn.execute(
                """SELECT source_message_id,status FROM conversation_open_loops
                   WHERE loop_type='question' AND source_message_id IN (40,41)"""
            ).fetchall()
        )
        self.assertEqual({40: "waiting", 41: "resolved"}, states)

    def test_answer_outside_bounded_window_does_not_resolve_question(self) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,50,'2026-08-23T09:00:00+00:00',
                       'Can we proceed with documents?',1,0)"""
        )
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_conversation(self.person_id, 10)
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (10,?,?,?,?,0)""",
            [
                (message_id, "2026-08-23T10:00:00+00:00", "Routine update", 1)
                for message_id in range(51, 171)
            ]
            + [
                (
                    171,
                    "2026-08-23T10:01:00+00:00",
                    "The documents were sent to legal today.",
                    0,
                )
            ],
        )

        service.refresh_conversation(self.person_id, 10)

        self.assertEqual(
            "waiting",
            self.conn.execute(
                """SELECT status FROM conversation_open_loops
                   WHERE loop_type='question' AND source_message_id=50"""
            ).fetchone()[0],
        )

    def test_person_scoped_answer_uses_contact_context_and_timeline_is_cited(
        self,
    ) -> None:
        self.conn.execute(
            """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
               source_chat_id,source_message_id,source_date,person_id,created_at,dedupe_key)
               VALUES (1,'note','Michael prefers email','Use email for updates.',
                       'informational','unknown',0.9,10,2,'2026-06-03T09:00:00+00:00',?,'now',
                       'michael-prefers-email')""",
            (self.person_id,),
        )
        service = ConversationContextService(self.conn, self.settings)
        service.refresh_person(self.person_id)
        answer, sources = answer_question(
            self.conn, "What is going on?", self.settings, person_id=self.person_id
        )
        self.assertIn("Confirm TBC pricing", answer)
        self.assertTrue(sources)
        timeline = service.timeline(self.person_id)
        self.assertTrue(any(item["kind"] == "event" for item in timeline))
        self.assertTrue(
            any(
                item["kind"] == "observation"
                and item["title"] == "Michael prefers email"
                for item in timeline
            )
        )

    def test_manual_person_merge_moves_materialized_contact_context(self) -> None:
        duplicate = EntityResolver(self.conn).person("Misha", source="manual")
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,
                   source_chat_id,due_date,confidence,created_at,updated_at)
               VALUES ('Confirm terms','confirm terms','Awaiting confirmation.','waiting','other',
                       ?,10,NULL,0.8,'2026-08-20T09:00:00+00:00','2026-08-20T09:00:00+00:00')""",
            (duplicate,),
        )
        ConversationContextService(self.conn, self.settings).refresh_person(duplicate)
        _merge_entities(self.conn, "person", self.person_id, [duplicate])
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM person_context_state WHERE person_id=?", (duplicate,)
            ).fetchone()
        )
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT 1 FROM person_context_state WHERE person_id=?",
                (self.person_id,),
            ).fetchone()
        )
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM current_conversation_context WHERE person_id=?",
                (duplicate,),
            ).fetchone()[0],
        )
        self.assertGreater(
            self.conn.execute(
                "SELECT COUNT(*) FROM conversation_open_loops WHERE person_id=?",
                (self.person_id,),
            ).fetchone()[0],
            0,
        )
