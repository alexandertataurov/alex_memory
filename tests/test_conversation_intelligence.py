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
