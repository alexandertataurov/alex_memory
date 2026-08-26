from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from alex_memory.context import ContextBuilder, ContextRequest, ContextService
from alex_memory.context.repository import current_facts, set_temporal_fact
from alex_memory.context.temporal import resolve_temporal_expressions
from alex_memory.database import connect
from alex_memory.ui.screens import show_context_view

from test_ai_pipeline import make_settings


class ContextEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        now = "2026-08-19T10:00:00+00:00"
        self.person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Michael',?,?)",
            (now, now),
        ).lastrowid
        self.project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Georgia LP',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO tasks(title,normalized_title,details,status,owner,related_person_id,related_project_id,source_chat_id,confidence,created_at,updated_at) VALUES ('Corporate documents','corporate documents','Waiting for documents','waiting','other',?,?,100,1,?,?)",
            (self.person_id, self.project_id, now, now),
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,1,?,'Documents requested',0,0)",
            (now,),
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (999,1,?,'Unrelated chat',0,0)",
            (now,),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_temporal_fact_preserves_history_and_as_of_state(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="corporate_documents_status",
            value={"status": "requested"},
            valid_from="2026-08-19",
            confidence=1,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="corporate_documents_status",
            value={"status": "received"},
            valid_from="2026-08-22",
            confidence=1,
        )
        self.assertEqual(
            "received",
            current_facts(self.conn, "person", self.person_id)[0]["value"]["status"],
        )
        self.assertEqual(
            "requested",
            current_facts(self.conn, "person", self.person_id, "2026-08-20")[0][
                "value"
            ]["status"],
        )

    def test_relative_and_dependency_time_keep_raw_expression(self) -> None:
        values = resolve_temporal_expressions(
            "I'll send it tomorrow morning, once compliance approves.",
            "2026-08-22T10:00:00+00:00",
            "Asia/Tbilisi",
        )
        self.assertTrue(any(value["resolved_at"] == "2026-08-23" for value in values))
        self.assertTrue(
            any(
                value["resolution_type"] == "dependency"
                and value["dependency_type"] == "compliance_approves"
                for value in values
            )
        )

    def test_person_context_is_bounded_and_excludes_unrelated_evidence(self) -> None:
        built = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(
                person_ids=[self.person_id],
                as_of=datetime.fromisoformat("2026-08-23T00:00:00+00:00"),
            )
        )
        self.assertEqual("Michael", built.people[0]["canonical_name"])
        self.assertTrue(built.tasks)
        self.assertEqual([], built.evidence)

    def test_global_snapshot_is_persisted(self) -> None:
        ContextService(self.conn, self.settings).snapshot_global_state()
        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) FROM global_state_snapshots").fetchone()[
                0
            ],
        )

    def test_context_view_renders_without_unrelated_table(self) -> None:
        class Context:
            def render(self, max_chars: int) -> str:
                self.max_chars = max_chars
                return "Bounded context"

        context = Context()
        output = StringIO()
        show_context_view(
            context, "Context", Console(file=output, force_terminal=False), 123
        )
        self.assertEqual(123, context.max_chars)
        self.assertIn("Bounded context", output.getvalue())
