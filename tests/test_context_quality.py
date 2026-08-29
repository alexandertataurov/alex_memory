from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from alex_memory.ai.repository import claim_ai_jobs, ensure_daily_jobs
from alex_memory.context import ContextBuilder, ContextRequest
from alex_memory.context.repository import (
    add_event,
    ensure_relationship,
    set_temporal_fact,
)
from alex_memory.database import connect
from alex_memory.operational import (
    EntityResolver,
    generate_daily_brief,
    normalize_task_title,
)
from test_ai_pipeline import make_settings


class ContextQualityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(
            Path(self.directory.name),
            context_max_raw_messages=3,
            context_max_events=8,
            context_max_graph_depth=2,
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
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.michael,
            predicate="corporate_documents_status",
            value={"status": "requested"},
            valid_from="2026-08-19",
            confidence=1.0,
            source_chat_id=100,
            source_message_id=1,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.michael,
            predicate="corporate_documents_status",
            value={"status": "received"},
            valid_from="2026-08-22",
            confidence=1.0,
            source_chat_id=100,
            source_message_id=3,
            conflict_policy="replace",
        )
        set_temporal_fact(
            self.conn,
            subject_type="project",
            subject_id=self.project,
            predicate="tbc_fx_pricing_status",
            value={"status": "unresolved"},
            valid_from="2026-08-21",
            confidence=0.95,
            source_chat_id=100,
            source_message_id=2,
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,details,status,owner,
               related_person_id,related_project_id,source_chat_id,confidence,created_at,updated_at)
               VALUES (?, ?, ?, 'open', 'me', ?, ?, 100, 1.0, ?, ?)""",
            (
                "Send flow-of-funds structure",
                normalize_task_title("Send flow-of-funds structure"),
                "Outstanding commitment for Georgia LP.",
                self.michael,
                self.project,
                self.now,
                self.now,
            ),
        )
        add_event(
            self.conn,
            event_type="project_updated",
            title="Hedge FX difference",
            description="George suggested hedging the FX difference if TBC pricing is high.",
            occurred_at="2026-08-21T10:00:00+00:00",
            person_id=self.george,
            project_id=self.project,
            source_chat_id=200,
            source_message_id=1,
            confidence=0.95,
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (?, ?, ?, ?, 0, 0)",
            [
                (100, 1, "2026-08-19T10:00:00+00:00", "Need corporate documents."),
                (
                    100,
                    2,
                    "2026-08-20T10:00:00+00:00",
                    "I will send the flow of funds tomorrow.",
                ),
                (
                    100,
                    3,
                    "2026-08-22T10:00:00+00:00",
                    "Docs received. Can we move forward?",
                ),
                (
                    200,
                    1,
                    "2026-08-21T10:00:00+00:00",
                    "If TBC spread is high we could hedge it.",
                ),
            ],
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_cross_chat_context_connects_project_without_misattribution(self) -> None:
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(
                purpose="message_analysis",
                chat_id=100,
                query="Can we move forward now?",
                as_of=datetime.fromisoformat("2026-08-22T12:00:00+00:00"),
            )
        )
        rendered = context.render_for_analysis(self.settings.context_max_chars)
        self.assertIn("Michael", rendered)
        self.assertIn("Georgia LP", rendered)
        self.assertIn("received", rendered)
        self.assertIn("unresolved", rendered)
        self.assertNotIn("Send flow-of-funds structure", rendered)
        self.assertEqual([], context.tasks)
        self.assertIn("Hedge FX difference", rendered)
        hedge = next(
            event for event in context.events if event["title"] == "Hedge FX difference"
        )
        self.assertEqual(self.george, hedge["person_id"])
        self.assertEqual(200, hedge["source_chat_id"])

    def test_as_of_context_does_not_leak_future_fact(self) -> None:
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(
                purpose="person_profile",
                person_ids=[self.michael],
                as_of=datetime.fromisoformat("2026-08-20T12:00:00+00:00"),
            )
        )
        document_fact = next(
            fact
            for fact in context.facts
            if fact["predicate"] == "corporate_documents_status"
        )
        self.assertEqual("requested", document_fact["value"]["status"])
        self.assertNotIn(
            "received", context.render_for_analysis(self.settings.context_max_chars)
        )

    def test_unresolved_question_does_not_receive_global_tasks_or_events(self) -> None:
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(purpose="ask_memory", query="unrelated unknown question")
        )

        self.assertEqual([], context.tasks)
        self.assertEqual([], context.events)

    def test_graph_depth_limits_related_people(self) -> None:
        shallow_settings = make_settings(
            Path(self.directory.name), context_max_graph_depth=1
        )
        context = ContextBuilder(self.conn, shallow_settings).build(
            ContextRequest(person_ids=[self.michael], purpose="person_profile")
        )
        self.assertEqual(
            ["Michael"], [person["canonical_name"] for person in context.people]
        )
        self.assertEqual(
            ["Georgia LP"], [project["canonical_name"] for project in context.projects]
        )

    def test_raw_evidence_stays_bounded(self) -> None:
        for message_id in range(4, 80):
            self.conn.execute(
                "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100, ?, ?, ?, 0, 0)",
                (
                    message_id,
                    f"2026-08-22T11:{message_id % 60:02d}:00+00:00",
                    f"Historical evidence {message_id}",
                ),
            )
        self.conn.commit()
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(person_ids=[self.michael], purpose="person_profile")
        )
        self.assertLessEqual(len(context.evidence), 3)
        self.assertGreater(context.context_score, 0)

    def test_supporting_evidence_uses_exact_canonical_messages_not_chat_recency(
        self,
    ) -> None:
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,99,?,'Unrelated newer message',0,0)",
            ("2026-08-22T11:59:00+00:00",),
        )
        self.conn.commit()

        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(person_ids=[self.michael], purpose="person_profile")
        )

        evidence_ids = {
            (item["chat_id"], item["message_id"]) for item in context.evidence
        }
        self.assertIn((100, 3), evidence_ids)
        self.assertNotIn((100, 99), evidence_ids)
        self.assertIn("EXACT SUPPORTING EVIDENCE", context.render(10000))

    def test_supporting_evidence_resolves_exact_claim_messages(self) -> None:
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,98,?,'Claim-backed source',0,0)",
            ("2026-08-22T11:58:00+00:00",),
        )
        claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,
               extractor_version,provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (1,'temporal_fact','Claim-backed fact','{}',2,'test','test',0.9,
               'accepted','context-claim-evidence','2026-08-22T11:58:00+00:00')"""
        ).lastrowid
        self.conn.execute(
            "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,100,98,?)",
            (claim_id, "2026-08-22T11:58:00+00:00"),
        )
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               observed_at,confidence,source_claim_id,created_at,updated_at)
               VALUES ('person',?,'claim_backed','{}','2026-08-22T11:58:00+00:00',
               '2026-08-22T11:58:00+00:00',0.9,?,?,?)""",
            (
                self.michael,
                claim_id,
                "2026-08-22T11:58:00+00:00",
                "2026-08-22T11:58:00+00:00",
            ),
        )
        self.conn.commit()

        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(person_ids=[self.michael], purpose="person_profile")
        )

        self.assertIn(
            (100, 98),
            {(item["chat_id"], item["message_id"]) for item in context.evidence},
        )

    def test_pinned_memory_and_conflicts_are_visible(self) -> None:
        self.conn.execute(
            "INSERT INTO pinned_memory(entity_type,entity_id,content,created_at,updated_at) VALUES ('person', ?, 'Michael is the primary decision maker.', ?, ?)",
            (self.michael, self.now, self.now),
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.michael,
            predicate="employment",
            value={"company": "ABC"},
            valid_from="2026-08-19",
            confidence=0.8,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.michael,
            predicate="employment",
            value={"company": "XYZ"},
            valid_from="2026-08-22",
            confidence=0.8,
        )
        self.conn.commit()
        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(person_ids=[self.michael], purpose="person_profile")
        )
        self.assertIn(
            "Michael is the primary decision maker.", context.people[0]["pinned"]
        )
        self.assertTrue(
            any(item["predicate"] == "employment" for item in context.conflicts)
        )

    def test_ai_jobs_receive_background_that_is_not_sourceable_as_new_message(
        self,
    ) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Michael','user')"
        )
        self.conn.execute(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100, 100, ?, 'Can we move forward now?', 0, 0)",
            (self.now,),
        )
        self.conn.commit()
        ensure_daily_jobs(self.conn, self.settings)
        _, batch = claim_ai_jobs(self.conn, "daily", 1, self.settings)[0]
        self.assertIn("<MEMORY_CONTEXT>", batch.prompt)
        self.assertIn("Memory context is background only", batch.prompt)
        self.assertIn("NEW <MESSAGE> window", batch.prompt)

    def test_daily_brief_persists_global_context_diagnostics(self) -> None:
        brief = generate_daily_brief(self.conn, "2026-08-22", self.settings)
        self.assertIn("global_context", brief)
        self.assertIn("context_diagnostics", brief)
        self.assertEqual("global_state", brief["context_diagnostics"]["purpose"])
