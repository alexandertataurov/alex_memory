from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.ai.repository import fetch_unclassified_messages, history_coverage
from alex_memory.classification import (
    CLASSIFICATION_VERSION,
    classify_message,
    save_classification,
)
from alex_memory.context.improver import ContextGraphImprover
from alex_memory.database import connect
from alex_memory.intelligence import retrieve
from alex_memory.models import AIMessage
from test_ai_pipeline import make_settings


class IntelligenceWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        self.now = "2026-08-22T10:00:00+00:00"
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type,updated_at) VALUES (100,'Work','user',?)",
            (self.now,),
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,1,?,'Please send the invoice today.',0,0)",
            (self.now,),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_versioned_classification_informs_retrieval_and_can_be_invalidated(
        self,
    ) -> None:
        message = AIMessage(
            100,
            1,
            None,
            self.now,
            "Please send the invoice today.",
            False,
            "Work",
            "user",
        )
        classification = classify_message(self.conn, message)
        self.assertEqual("request", classification.content_type)
        self.assertEqual("high", classification.importance)
        save_classification(self.conn, message, classification)
        self.conn.commit()

        result = next(
            item
            for item in retrieve(self.conn, "invoice", self.settings)
            if item.message_id == 1
        )
        self.assertGreaterEqual(result.score, 55)
        self.assertFalse(
            fetch_unclassified_messages(
                self.conn, 10, self.settings, CLASSIFICATION_VERSION
            )
        )
        self.conn.execute(
            "UPDATE message_classifications SET context_stale=1 WHERE chat_id=100 AND message_id=1"
        )
        self.conn.commit()
        self.assertEqual(
            [1],
            [
                item.message_id
                for item in fetch_unclassified_messages(
                    self.conn, 10, self.settings, CLASSIFICATION_VERSION
                )
            ],
        )
        self.assertEqual(0, history_coverage(self.conn, self.settings)["classified"])

    def test_v2_reclassification_is_selective_and_preserves_manual_review(self):
        now = self.now
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (100,?,?,?,0,0)""",
            [
                (2, now, "Low-value archive note."),
                (3, now, "Please send the signed contract."),
                (4, now, "Forwarded private invoice."),
            ],
        )
        self.conn.executemany(
            """INSERT INTO message_classifications(
                   chat_id,message_id,conversation_type,content_type,actionability,
                   importance,content_scope,information_scope,temporal_relevance,
                   potential_state_change,is_forwarded,topic_json,classifier_type,
                   confidence,classification_version,context_version,context_stale,
                   classified_at
               ) VALUES (100,?,'personal',?,?,?,?,?,'dated',0,?,'[]','test',1.0,1,1,0,?)""",
            [
                (
                    2,
                    "information",
                    "informational",
                    "low",
                    "personal",
                    "personal",
                    0,
                    now,
                ),
                (3, "request", "actionable", "high", "business", "business", 0, now),
                (
                    4,
                    "information",
                    "informational",
                    "normal",
                    "unknown",
                    "unknown",
                    1,
                    now,
                ),
            ],
        )
        self.conn.execute(
            """INSERT INTO review_queue(
                   review_type,subject_type,subject_id,payload_json,confidence,status,created_at,resolved_at
               ) VALUES ('message_classification','message',3,'{}',1.0,'approved',?,?)""",
            (now, now),
        )
        self.conn.commit()
        pending = fetch_unclassified_messages(
            self.conn, 10, self.settings, CLASSIFICATION_VERSION
        )
        pending_ids = {message.message_id for message in pending}
        self.assertIn(4, pending_ids)
        self.assertNotIn(2, pending_ids)
        self.assertNotIn(3, pending_ids)

    def test_graph_improvement_is_chat_bounded_source_backed_and_idempotent(
        self,
    ) -> None:
        person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Mika',?,?)",
            (self.now, self.now),
        ).lastrowid
        project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Atlas',?,?)",
            (self.now, self.now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,related_project_id,
               source_chat_id,confidence,created_at,updated_at)
               VALUES ('Send docs','send docs','open','me',?,?,100,1.0,?,?)""",
            (person_id, project_id, self.now, self.now),
        )
        self.conn.execute(
            """INSERT INTO message_classifications(chat_id,message_id,conversation_type,content_type,
               actionability,importance,content_scope,temporal_relevance,potential_state_change,
               topic_json,classifier_type,confidence,classification_version,context_version,
               context_stale,classified_at)
               VALUES (100,1,'personal','request','actionable','high','business','current',1,
                       '[]','test',1.0,1,1,0,?)""",
            (self.now,),
        )
        self.conn.commit()

        improver = ContextGraphImprover(self.conn)
        first = improver.improve(source_chat_id=100)
        second = improver.improve(source_chat_id=100)
        self.assertGreater(first.relationships_added, 0)
        self.assertEqual(0, second.relationships_added)
        self.assertEqual(1, first.affected_chats)
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT context_stale FROM message_classifications WHERE chat_id=100 AND message_id=1"
            ).fetchone()[0],
        )
        self.assertEqual(
            {
                ("conversation",),
                ("global",),
                ("person",),
                ("project",),
                ("task",),
            },
            {
                (scope_type,)
                for scope_type, _scope_id in self.conn.execute(
                    "SELECT scope_type,scope_id FROM context_invalidations"
                )
            },
        )
