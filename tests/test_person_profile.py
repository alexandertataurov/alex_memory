from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from rich.console import Console
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from alex_memory.models import AIAnalysisResult
from alex_memory.person_profile import (
    _action_items,
    build_person_profile,
    profile_summary_package,
)
from alex_memory.ai.repository import claim_ai_jobs, save_ai_success
from alex_memory.profile_enrichment import (
    drain_queued_profile_scan,
    enrich_person,
    profile_scan_debug,
    profile_scan_status,
    queue_profile_scan,
)
from alex_memory.profile_summary import (
    refresh_all_person_profiles,
    refresh_profile_summary,
)
from alex_memory.ui.profile import show_profile
from alex_memory.ui.textual_app import _profile_sections
from test_ai_pipeline import make_settings
from alex_memory.database import connect
from alex_memory.profile_enrichment import PROFILE_EXTRACTOR_VERSION
from alex_memory.telegram.normalize import normalize_message


class _SummaryRouter:
    async def analyze(self, batch, **_kwargs):
        return AIAnalysisResult(
            "test",
            "test-model",
            "Waiting for documents. [100/1]",
            [],
            raw_payload={"summary": "Waiting for documents. [100/1]", "items": []},
        )


class PersonProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(
            Path(self.directory.name), ai_profile_summaries_enabled=True
        )
        self.conn = connect(self.settings)
        now = "2026-08-24T12:00:00+00:00"
        self.person_id = self.conn.execute(
            """INSERT INTO people(canonical_name,telegram_user_id,telegram_username,created_at,updated_at)
               VALUES ('Michael',100,'michael',?,?)""",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO entity_aliases(entity_type,entity_id,alias,normalized_alias,created_at) VALUES ('person',?,'Mikhail','mikhail',?)",
            (self.person_id, now),
        )
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Michael','user')"
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,?,0)",
            [
                (1, 100, now, "I am waiting for the corporate documents.", 0),
                (2, 100, now, "Unrelated newer message.", 0),
            ],
        )
        claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,extractor_version,
               provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (1,'temporal_fact','Document status','{}',2,'test','test',0.9,'accepted','profile-claim',?)""",
            (now,),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,100,1,?)",
            (claim_id, now),
        )
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,observed_at,
               confidence,source_claim_id,created_at,updated_at) VALUES ('person',?,'capability','{"role":"legal"}',?, ?,0.9,?,?,?)""",
            (self.person_id, now, now, claim_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,source_chat_id,
               confidence,source_claim_id,created_at,updated_at) VALUES ('Send documents','send documents','waiting','other',?,100,0.9,?,?,?)""",
            (self.person_id, claim_id, now, now),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_profile_is_bounded_and_uses_exact_claim_evidence(self) -> None:
        profile = build_person_profile(self.conn, int(self.person_id))
        self.assertEqual(["Mikhail"], profile["aliases"])
        self.assertEqual("legal", profile["facts"][0]["value"]["role"])
        self.assertEqual(
            [(100, 1)],
            [
                (item["chat_id"], item["message_id"])
                for item in profile["facts"][0]["evidence"]
            ],
        )
        self.assertEqual(2, profile["stats"]["total"])
        self.assertEqual(2, profile["stats"]["conversations"][0]["incoming"])

    def test_audit_normalization_keeps_only_explicit_forward_metadata(self) -> None:
        base = {
            "id": 1,
            "sender_id": 100,
            "date": datetime(2026, 8, 24, tzinfo=UTC),
            "raw_text": "Quoted or copied assertion",
            "out": False,
            "media": None,
        }
        known_forward = SimpleNamespace(
            **base,
            fwd_from=SimpleNamespace(from_name="Known origin", from_id=None),
            reply_to=None,
        )
        hidden_forward = SimpleNamespace(
            **base,
            fwd_from=SimpleNamespace(from_name=None, from_id=None, channel_post=None),
            reply_to=None,
        )
        reply = SimpleNamespace(
            **base,
            fwd_from=None,
            reply_to=SimpleNamespace(reply_to_msg_id=99),
        )
        copied = SimpleNamespace(**base, fwd_from=None, reply_to=None)

        self.assertEqual((1, "Known origin"), normalize_message(100, known_forward)[8:])
        self.assertEqual((1, None), normalize_message(100, hidden_forward)[8:])
        reply_data = normalize_message(100, reply)
        self.assertEqual(99, reply_data[5])
        self.assertEqual((0, None), reply_data[8:])
        self.assertEqual((0, None), normalize_message(100, copied)[8:])

    def test_profile_omits_canonical_records_without_exact_evidence(self) -> None:
        claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(
                   batch_id,claim_type,statement,payload_json,extractor_version,provider,
                   model,confidence,authority_status,dedupe_key,created_at
               ) VALUES (1,'temporal_fact','Unsupported','{}',2,'test','test',0.9,
                         'accepted','unsupported-profile-claim','now')"""
        ).lastrowid
        assert claim_id is not None
        self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,observed_at,
                   confidence,source_claim_id,created_at,updated_at
               ) VALUES ('person',?,'unsupported','{}','now','now',0.9,?,'now','now')""",
            (self.person_id, claim_id),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(self.person_id))

        self.assertEqual(
            ["capability"], [fact["predicate"] for fact in profile["facts"]]
        )

    def test_profile_facts_have_human_labels_and_suppress_placeholders(self) -> None:
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,observed_at,
               confidence,source_claim_id,created_at,updated_at)
               VALUES ('person',?,'relationship.history','"History"',?, ?,0.9,?,?,?)""",
            (self.person_id, "now", "now", 1, "now", "now"),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(self.person_id))

        capability = next(
            fact for fact in profile["facts"] if fact["predicate"] == "capability"
        )
        self.assertEqual("Capabilities", capability["display_section"])
        self.assertEqual("Capability", capability["display_label"])
        self.assertEqual("legal", capability["display_value"])
        self.assertNotIn(
            "relationship.history", [fact["predicate"] for fact in profile["facts"]]
        )

    def test_profile_facts_show_only_the_direct_closed_interval_predecessor(
        self,
    ) -> None:
        current_id, claim_id = self.conn.execute(
            "SELECT fact_id,source_claim_id FROM context_facts WHERE predicate='capability'"
        ).fetchone()
        self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,valid_to,is_current,
                   superseded_by_fact_id,observed_at,confidence,source_claim_id,created_at,updated_at
               ) VALUES ('person',?,'capability','{"role":"contracts"}',?, ?,0,?,?,0.9,?,?,?)""",
            (
                self.person_id,
                "2026-07-01T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
                current_id,
                "2026-08-24T12:00:00+00:00",
                claim_id,
                "2026-08-24T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
            ),
        )
        self.conn.commit()

        facts = [
            fact
            for fact in build_person_profile(self.conn, int(self.person_id))["facts"]
            if fact["predicate"] == "capability"
        ]

        self.assertEqual(
            ["Now", "Previously"], [fact["temporal_state"] for fact in facts]
        )
        self.assertEqual(
            ["legal", "contracts"], [fact["display_value"] for fact in facts]
        )
        self.assertTrue(all(fact["evidence"] for fact in facts))
        self.assertIn("Now — Capabilities", _profile_sections(facts))
        self.assertIn("Previously — Capabilities", _profile_sections(facts))
        output = StringIO()
        show_profile(
            build_person_profile(self.conn, int(self.person_id)),
            "person",
            Console(file=output, force_terminal=False, width=160),
            section="context",
        )
        self.assertIn("Now — Capabilities", output.getvalue())
        self.assertIn("Previously — Capabilities", output.getvalue())

    def test_profile_facts_fail_closed_for_an_unclosed_prior_interval(self) -> None:
        current_id, claim_id = self.conn.execute(
            "SELECT fact_id,source_claim_id FROM context_facts WHERE predicate='capability'"
        ).fetchone()
        self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,valid_to,is_current,
                   superseded_by_fact_id,observed_at,confidence,source_claim_id,created_at,updated_at
               ) VALUES ('person',?,'capability','{"role":"unclosed"}',?,NULL,0,?,?,0.9,?,?,?)""",
            (
                self.person_id,
                "2026-07-01T12:00:00+00:00",
                current_id,
                "2026-08-24T12:00:00+00:00",
                claim_id,
                "2026-08-24T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
            ),
        )
        self.conn.commit()

        facts = [
            fact
            for fact in build_person_profile(self.conn, int(self.person_id))["facts"]
            if fact["predicate"] == "capability"
        ]

        self.assertEqual(["Now"], [fact["temporal_state"] for fact in facts])

    def test_profile_derives_an_evidence_complete_role_change(self) -> None:
        claim_id = self.conn.execute(
            "SELECT source_claim_id FROM context_facts WHERE predicate='capability'"
        ).fetchone()[0]
        current_id = self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,observed_at,
                   confidence,source_claim_id,created_at,updated_at
               ) VALUES ('person',?,'professional.role','"Legal lead"',?,?,0.9,?,?,?)""",
            (
                self.person_id,
                "2026-08-24T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
                claim_id,
                "2026-08-24T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
            ),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO context_facts(
                   subject_type,subject_id,predicate,value_json,valid_from,valid_to,is_current,
                   superseded_by_fact_id,observed_at,confidence,source_claim_id,created_at,updated_at
               ) VALUES ('person',?,'professional.role','"Counsel"',?, ?,0,?,?,0.9,?,?,?)""",
            (
                self.person_id,
                "2026-07-01T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
                current_id,
                "2026-08-24T12:00:00+00:00",
                claim_id,
                "2026-08-24T12:00:00+00:00",
                "2026-08-24T12:00:00+00:00",
            ),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(self.person_id))

        self.assertEqual(
            ["Counsel → Legal lead"],
            [change["display_value"] for change in profile["changes"]],
        )
        self.assertEqual("Changed", profile["changes"][0]["temporal_state"])
        self.assertTrue(profile["changes"][0]["evidence"])
        self.assertIn("Changed — Changes", _profile_sections(profile["changes"]))
        output = StringIO()
        show_profile(
            profile,
            "person",
            Console(file=output, force_terminal=False, width=160),
            section="context",
        )
        self.assertIn("Changed — Changes", output.getvalue())
        self.assertIn("Counsel → Legal lead", output.getvalue())

    def test_profile_exposes_pending_raw_conversation_evidence(self) -> None:
        self.conn.execute(
            """INSERT INTO current_conversation_context(
                   person_id,source_type,conversation_id,chat_id,evidence_through_at,updated_at
               ) VALUES (?, 'telegram', '100', 100, '2026-08-23T12:00:00+00:00', 'now')""",
            (self.person_id,),
        )
        profile = build_person_profile(self.conn, int(self.person_id))
        self.assertEqual(
            "new raw evidence pending", profile["context_freshness"]["state"]
        )

    def test_profile_topics_reject_generic_materialized_tokens(self) -> None:
        self.conn.execute(
            """INSERT INTO current_conversation_context(
                   person_id,source_type,conversation_id,chat_id,topic_json,updated_at
               ) VALUES (?, 'telegram', '100', 100, ?, 'now')""",
            (self.person_id, '["sender", "details", "for", "Contract renewal"]'),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(self.person_id))

        self.assertEqual(["contract renewal"], profile["topics"])

    def test_actions_keep_workflow_staleness_and_uncertainty_separate(self) -> None:
        self.conn.executemany(
            """INSERT INTO tasks(
                   title,normalized_title,status,owner,related_person_id,source_chat_id,
                   confidence,manual_status_locked,created_at,updated_at
               ) VALUES (?,?,?,?,?,?,?,1,?,?)""",
            [
                (
                    "Act now",
                    "act now",
                    "open",
                    "me",
                    self.person_id,
                    100,
                    1.0,
                    "2026-09-03",
                    "2026-09-03",
                ),
                (
                    "Waiting old",
                    "waiting old",
                    "waiting",
                    "other",
                    self.person_id,
                    100,
                    0.1,
                    "2026-07-01",
                    "2026-07-01",
                ),
                (
                    "Blocked old",
                    "blocked old",
                    "blocked",
                    "me",
                    self.person_id,
                    100,
                    0.1,
                    "2026-07-01",
                    "2026-07-01",
                ),
                (
                    "Stale open",
                    "stale open",
                    "open",
                    "me",
                    self.person_id,
                    100,
                    1.0,
                    "2026-07-01",
                    "2026-07-01",
                ),
            ],
        )
        self.conn.commit()
        changes_before = self.conn.total_changes

        profile = build_person_profile(self.conn, int(self.person_id))
        actions = _action_items(profile, as_of=datetime(2026, 9, 3, tzinfo=UTC))

        self.assertEqual(changes_before, self.conn.total_changes)
        by_title = {item["title"]: item for item in actions}
        self.assertEqual("blocked", by_title["Blocked old"]["workflow_state"])
        self.assertTrue(by_title["Blocked old"]["is_stale"])
        self.assertEqual("uncertain", by_title["Blocked old"]["certainty"])
        self.assertEqual("BLOCKED", by_title["Blocked old"]["action_state"])
        self.assertTrue(by_title["Waiting old"]["is_stale"])
        self.assertEqual("uncertain", by_title["Waiting old"]["certainty"])
        self.assertEqual("WAITING", by_title["Waiting old"]["action_state"])
        self.assertEqual(
            ["Act now", "Waiting old", "Blocked old", "Stale open"],
            [
                item["title"]
                for item in actions
                if item["title"]
                in {"Act now", "Waiting old", "Blocked old", "Stale open"}
            ],
        )

    def test_relationship_other_endpoint_uses_type_and_id(self) -> None:
        now = "2026-08-24T12:00:00+00:00"
        company_id = self.conn.execute(
            "INSERT INTO companies(canonical_name,created_at,updated_at) VALUES ('Atlas',?,?)",
            (now, now),
        ).lastrowid
        assert company_id == self.person_id
        self.conn.execute(
            """INSERT INTO relationships(
                   from_type,from_id,to_type,to_id,relationship_type,valid_from,
                   confidence,source_chat_id,source_message_id,created_at,updated_at
               ) VALUES ('company',?,'person',?,'advises',?,0.9,100,1,?,?)""",
            (company_id, self.person_id, now, now, now),
        )
        self.conn.commit()

        relationship = build_person_profile(self.conn, int(self.person_id))[
            "relationships"
        ][0]

        self.assertEqual(
            ("company", company_id, "Atlas"),
            (
                relationship["other_type"],
                relationship["other_id"],
                relationship["other_name"],
            ),
        )

    def test_group_messages_and_stats_exclude_unrelated_participants(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (200,'Atlas group','group')"
        )
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (200,?,?,?,?,?,0)""",
            [
                (1, 100, "2026-08-25T12:00:00+00:00", "Michael update", 0),
                (2, 777, "2026-08-25T12:01:00+00:00", "Unrelated participant", 0),
                (3, 999, "2026-08-25T12:02:00+00:00", "My group reply", 1),
            ],
        )
        self.conn.execute(
            """INSERT INTO ai_items(batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,person_id,created_at,dedupe_key)
               VALUES (1,'event','Michael update','','informational','unknown',0.9,200,1,
                       '2026-08-25T12:00:00+00:00',?,'now','group-profile-link')""",
            (self.person_id,),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(self.person_id))
        group_messages = [
            item for item in profile["messages"] if item["chat_id"] == 200
        ]
        group_stats = next(
            item for item in profile["stats"]["conversations"] if item["chat_id"] == 200
        )

        self.assertEqual({1, 3}, {item["message_id"] for item in group_messages})
        self.assertEqual(
            {"Contact", "You"}, {item["speaker"] for item in group_messages}
        )
        self.assertEqual(2, group_stats["total"])
        self.assertEqual(4, profile["stats"]["total"])

    def test_profile_summary_is_cited_and_presentation_only(self) -> None:
        before = self.conn.execute("SELECT COUNT(*) FROM context_facts").fetchone()[0]
        self.assertTrue(
            asyncio.run(
                refresh_profile_summary(
                    self.conn,
                    self.settings,
                    int(self.person_id),
                    router=_SummaryRouter(),
                )
            )
        )
        self.assertEqual(
            before,
            self.conn.execute("SELECT COUNT(*) FROM context_facts").fetchone()[0],
        )
        self.assertEqual(
            "Waiting for documents. [100/1]",
            self.conn.execute(
                "SELECT profile_summary FROM person_context_state WHERE person_id=?",
                (self.person_id,),
            ).fetchone()[0],
        )
        self.assertFalse(
            asyncio.run(
                refresh_profile_summary(
                    self.conn,
                    self.settings,
                    int(self.person_id),
                    router=_SummaryRouter(),
                )
            )
        )

        self.conn.execute(
            "UPDATE context_facts SET value_json=? WHERE fact_id=1",
            ('{"role":"contracts"}',),
        )
        self.conn.commit()
        self.assertTrue(
            asyncio.run(
                refresh_profile_summary(
                    self.conn,
                    self.settings,
                    int(self.person_id),
                    router=_SummaryRouter(),
                )
            )
        )

    def test_manual_profile_scan_has_exact_bounded_membership_and_no_auto_queue(
        self,
    ) -> None:
        self.assertEqual(
            0, profile_scan_status(self.conn, int(self.person_id))["pending"]
        )
        self.assertTrue(
            profile_scan_status(self.conn, int(self.person_id))["direct_chat_available"]
        )
        self.assertEqual(
            2, profile_scan_status(self.conn, int(self.person_id))["eligible_messages"]
        )
        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )
        row = self.conn.execute(
            "SELECT job_id,lane,profile_person_id,profile_extractor_version,status FROM ai_jobs WHERE profile_person_id=?",
            (self.person_id,),
        ).fetchone()
        self.assertEqual(
            ("profile", self.person_id, PROFILE_EXTRACTOR_VERSION, "pending"),
            row[1:],
        )
        membership = self.conn.execute(
            "SELECT chat_id,message_id FROM ai_job_messages WHERE job_id=? ORDER BY ordinal",
            (row[0],),
        ).fetchall()
        self.assertEqual([(100, 1), (100, 2)], membership)
        claimed = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )
        self.assertEqual(1, len(claimed))
        self.assertEqual(
            [(100, 1), (100, 2)],
            [
                (message.chat_id, message.message_id)
                for message in claimed[0][1].messages
            ],
        )
        self.assertEqual(
            0,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )

    def test_profile_scan_represents_all_eligible_messages_in_bounded_windows(
        self,
    ) -> None:
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,?,0)",
            [
                (index, 100, f"2026-08-2{index}T12:00:00+00:00", f"Message {index}", 0)
                for index in range(3, 7)
            ],
        )
        settings = replace(
            self.settings,
            history_internal_batch_messages=2,
            history_internal_batch_chars=100,
        )
        self.conn.commit()

        self.assertEqual(
            6, queue_profile_scan(self.conn, settings, int(self.person_id))
        )
        status = profile_scan_status(self.conn, int(self.person_id))
        self.assertEqual(6, status["eligible_messages"])
        self.assertEqual(6, status["pending_messages"])
        self.assertEqual(0, status["unqueued_messages"])

        first_job, first_count = self.conn.execute(
            "SELECT job_id,message_count FROM ai_jobs WHERE profile_person_id=? ORDER BY job_id LIMIT 1",
            (self.person_id,),
        ).fetchone()
        self.conn.execute(
            "UPDATE ai_jobs SET status='done' WHERE job_id=?", (first_job,)
        )
        self.conn.commit()
        status = profile_scan_status(self.conn, int(self.person_id))
        self.assertEqual(first_count, status["completed_messages"])
        self.assertEqual(6 - first_count, status["pending_messages"])
        self.assertEqual(0, status["unqueued_messages"])

    def test_profile_scan_retries_only_explicit_failed_membership(self) -> None:
        self.assertEqual(
            1, queue_profile_scan(self.conn, self.settings, int(self.person_id))
        )
        self.conn.execute(
            "UPDATE ai_jobs SET status='failed' WHERE profile_person_id=?",
            (self.person_id,),
        )
        self.conn.commit()

        with patch(
            "alex_memory.profile_enrichment._process_profile_jobs",
            new_callable=AsyncMock,
        ) as process:
            result = asyncio.run(
                enrich_person(
                    self.conn,
                    self.settings,
                    Console(file=StringIO()),
                    int(self.person_id),
                    limit=1,
                )
            )

        self.assertEqual(1, result["retried"])
        self.assertEqual(1, len(process.await_args.args[4]))
        self.assertEqual(
            "running",
            self.conn.execute(
                "SELECT status FROM ai_jobs WHERE profile_person_id=?",
                (self.person_id,),
            ).fetchone()[0],
        )

    def test_profile_scan_status_is_read_only(self) -> None:
        self.conn.execute("PRAGMA query_only=ON")
        try:
            status = profile_scan_status(self.conn, int(self.person_id))
        finally:
            self.conn.execute("PRAGMA query_only=OFF")
        self.assertEqual(2, status["eligible_messages"])

    def test_profile_scan_debug_is_bounded_metadata_not_message_content(self) -> None:
        self.conn.execute(
            "UPDATE semantic_claims SET profile_person_id=?,profile_assertion_kind='direct' "
            "WHERE claim_id=1",
            (self.person_id,),
        )
        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )

        debug = profile_scan_debug(self.conn, int(self.person_id))

        self.assertEqual(1, debug["direct_claims"])
        self.assertEqual(0, debug["third_party_claims"])
        self.assertEqual(0, debug["inference_claims"])
        self.assertEqual(0, debug["rejected_items"])
        self.assertEqual([], debug["rejection_reasons"])
        self.assertEqual(1, len(debug["jobs"]))
        self.assertEqual("pending", debug["jobs"][0][1])
        self.assertNotIn("corporate documents", repr(debug))

    def test_profile_scan_status_uses_only_the_current_extractor_version(self) -> None:
        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )
        self.conn.execute(
            "UPDATE ai_jobs SET profile_extractor_version=1 WHERE profile_person_id=?",
            (self.person_id,),
        )
        self.conn.commit()

        status = profile_scan_status(self.conn, int(self.person_id))

        self.assertEqual(0, status["pending"])
        self.assertEqual(0, status["completed_messages"])
        self.assertEqual(2, status["eligible_messages"])
        self.assertEqual(
            [],
            claim_ai_jobs(
                self.conn,
                "profile",
                1,
                self.settings,
                profile_person_id=int(self.person_id),
                profile_extractor_version=PROFILE_EXTRACTOR_VERSION,
            ),
        )

    def test_profile_scan_status_requires_current_analysis_version(self) -> None:
        self.assertEqual(
            1, queue_profile_scan(self.conn, self.settings, int(self.person_id))
        )
        self.conn.execute(
            "UPDATE ai_jobs SET analysis_version=1 WHERE profile_person_id=?",
            (self.person_id,),
        )
        self.conn.commit()

        status = profile_scan_status(self.conn, int(self.person_id))

        self.assertEqual(0, status["pending"])
        self.assertEqual(0, status["pending_messages"])
        self.assertEqual(2, status["unqueued_messages"])
        self.assertEqual(
            1, queue_profile_scan(self.conn, self.settings, int(self.person_id))
        )

    def test_profile_scan_requires_a_resolved_person_author(
        self,
    ) -> None:
        self.conn.execute(
            "UPDATE people SET telegram_user_id=NULL WHERE person_id=?",
            (self.person_id,),
        )
        self.conn.commit()
        status = profile_scan_status(self.conn, int(self.person_id))
        self.assertTrue(status["direct_chat_available"])
        self.assertEqual(0, status["eligible_messages"])
        self.assertEqual(
            0,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )

    def test_profile_scan_processes_backlog_before_queueing_more(self) -> None:
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,?,0)",
            [
                (index, 100, f"2026-08-2{index}T12:00:00+00:00", f"Message {index}", 0)
                for index in range(3, 7)
            ],
        )
        settings = replace(
            self.settings,
            history_internal_batch_messages=2,
            history_internal_batch_chars=100,
        )
        self.conn.commit()
        self.assertEqual(
            6, queue_profile_scan(self.conn, settings, int(self.person_id))
        )
        with patch(
            "alex_memory.profile_enrichment._process_profile_jobs",
            new_callable=AsyncMock,
        ) as process:
            result = asyncio.run(
                enrich_person(
                    self.conn, settings, Console(file=StringIO()), int(self.person_id)
                )
            )
        self.assertEqual(0, result["queued"])
        self.assertEqual(2, process.await_args.args[4].__len__())
        self.assertEqual(
            4,
            self.conn.execute(
                "SELECT COUNT(*) FROM ai_jobs WHERE profile_person_id=? AND status='pending'",
                (self.person_id,),
            ).fetchone()[0],
        )

    def test_drain_profile_scan_claims_only_existing_pending_windows(self) -> None:
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,?,0)",
            [
                (index, 100, f"2026-08-2{index}T12:00:00+00:00", f"Message {index}", 0)
                for index in range(3, 7)
            ],
        )
        settings = replace(
            self.settings,
            history_internal_batch_messages=2,
            history_internal_batch_chars=100,
        )
        self.conn.commit()
        self.assertEqual(
            6, queue_profile_scan(self.conn, settings, int(self.person_id))
        )
        with patch(
            "alex_memory.profile_enrichment._process_profile_jobs",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                drain_queued_profile_scan(
                    self.conn, settings, Console(file=StringIO()), int(self.person_id)
                )
            )
        self.assertEqual(6, result["processed"])
        self.assertEqual(
            0,
            self.conn.execute(
                "SELECT COUNT(*) FROM ai_jobs WHERE profile_person_id=? AND status='pending'",
                (self.person_id,),
            ).fetchone()[0],
        )

    def test_profile_scan_claims_self_authored_group_evidence(self) -> None:
        self.conn.execute("UPDATE messages SET is_deleted=1 WHERE chat_id=100")
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (200,'Project group','group')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (200,1,100,'2026-08-25T12:00:00+00:00','I can prepare the contract.',0,0)"""
        )
        self.conn.commit()

        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )
        claimed = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )
        self.assertEqual(
            [(200, 1)],
            [
                (message.chat_id, message.message_id)
                for message in claimed[0][1].messages
            ],
        )

    def test_profile_scan_includes_only_resolved_claim_linked_mentions(self) -> None:
        self.conn.execute("UPDATE messages SET is_deleted=1 WHERE chat_id=100")
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (200,'Project group','group')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (200,1,777,'2026-08-25T12:00:00+00:00','Michael discussed Bank X.',0,0)"""
        )
        claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,extractor_version,
               provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (2,'relationship','Mention','{}',2,'test','test',0.8,'observed','resolved-mention','2026-08-25')"""
        ).lastrowid
        self.conn.execute(
            "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,200,1,'2026-08-25')",
            (claim_id,),
        )
        self.conn.execute(
            """INSERT INTO semantic_claim_entity_refs(claim_id,ordinal,role,entity_type,surface_name,
               canonical_entity_id,resolution_status,created_at)
               VALUES (?,0,'subject','person','Michael',?,'resolved','2026-08-25')""",
            (claim_id, self.person_id),
        )
        self.conn.commit()

        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )
        job_id, work = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )[0]
        self.assertEqual(
            [(200, 1)], [(item.chat_id, item.message_id) for item in work.messages]
        )
        self.assertEqual(
            job_id,
            self.conn.execute(
                "SELECT job_id FROM ai_jobs WHERE job_id=?", (job_id,)
            ).fetchone()[0],
        )

    def test_profile_scan_uses_full_direct_context_but_rejects_owner_evidence(
        self,
    ) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (100,3,999,'2026-08-25T12:00:00+00:00','Please send the contract.',1,0)"""
        )
        self.conn.commit()

        self.assertEqual(
            1,
            queue_profile_scan(self.conn, self.settings, int(self.person_id)),
        )
        job_id, work = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )[0]
        self.assertEqual(
            [(100, 1), (100, 2), (100, 3)],
            [(message.chat_id, message.message_id) for message in work.messages],
        )
        result = save_ai_success(
            self.conn,
            work,
            {
                "summary": "Forwarded profile assertion.",
                "items": [
                    {
                        "kind": "important_fact",
                        "title": "Can prepare contracts",
                        "details": "",
                        "status": "informational",
                        "owner": "other",
                        "due_date": None,
                        "person": "Michael",
                        "company": None,
                        "project_name": None,
                        "amount": None,
                        "currency": None,
                        "confidence": 0.8,
                        "source_chat_id": 100,
                        "source_message_id": 3,
                    }
                ],
            },
            self.settings,
            lane="profile",
            job_id=job_id,
        )
        self.assertEqual(1, result.rejected)
        self.assertEqual(0, result.claims_inserted)
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) FROM ai_items").fetchone()[0]
        )

    def test_forwarded_text_cannot_be_accepted_as_a_direct_profile_claim(
        self,
    ) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media,
               is_forwarded,forward_source) VALUES (100,3,100,'2026-08-25T12:00:00+00:00',
               'I founded Forwarded Co.',0,0,1,'Known origin')"""
        )
        self.conn.commit()
        queue_profile_scan(self.conn, self.settings, int(self.person_id))
        job_id, work = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )[0]

        result = save_ai_success(
            self.conn,
            work,
            {
                "summary": "Forwarded profile assertion.",
                "items": [
                    {
                        "kind": "important_fact",
                        "title": "professional.role: Founder",
                        "details": "",
                        "status": "informational",
                        "owner": "other",
                        "due_date": None,
                        "person": "Michael",
                        "company": "Forwarded Co.",
                        "project_name": None,
                        "amount": None,
                        "currency": None,
                        "confidence": 0.9,
                        "source_chat_id": 100,
                        "source_message_id": 3,
                        "assertion_kind": "direct",
                        "effective_from": None,
                        "effective_to": None,
                    }
                ],
            },
            self.settings,
            lane="profile",
            job_id=job_id,
        )

        self.assertEqual(1, result.rejected)
        self.assertEqual(0, result.claims_inserted)
        self.assertIn(
            "profile item source must be authored by the selected person",
            result.rejection_reasons[0],
        )

    def test_profile_third_party_claim_is_traceable_but_not_canonical(self) -> None:
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (100,3,999,'2026-08-25T12:00:00+00:00','Michael used to work at Bank X.',1,0)"""
        )
        self.conn.commit()
        queue_profile_scan(self.conn, self.settings, int(self.person_id))
        job_id, work = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            self.settings,
            profile_person_id=int(self.person_id),
        )[0]
        result = save_ai_success(
            self.conn,
            work,
            {
                "summary": "profile claim",
                "items": [
                    {
                        "kind": "important_fact",
                        "title": "professional.previous_role: Bank X",
                        "details": "Reported by another participant.",
                        "status": "informational",
                        "owner": "other",
                        "due_date": None,
                        "person": "Michael",
                        "company": "Bank X",
                        "project_name": None,
                        "amount": None,
                        "currency": None,
                        "confidence": 0.8,
                        "source_chat_id": 100,
                        "source_message_id": 3,
                        "assertion_kind": "third_party",
                        "effective_from": None,
                        "effective_to": None,
                    }
                ],
            },
            self.settings,
            lane="profile",
            job_id=job_id,
        )
        self.assertEqual(1, result.claims_inserted, result.rejection_reasons)
        self.assertEqual(0, result.inserted)
        profile = build_person_profile(self.conn, int(self.person_id))
        self.assertEqual("third_party", profile["uncertain"][0]["assertion_kind"])
        self.assertEqual("You", profile["uncertain"][0]["evidence"][0]["speaker"])
        package = profile_summary_package(self.conn, int(self.person_id))
        self.assertNotIn(
            "profile_claims", [record["section"] for record in package["records"]]
        )

    def test_full_profile_refresh_reuses_canonical_state_without_ai(self) -> None:
        outcome = asyncio.run(
            refresh_all_person_profiles(
                self.conn, replace(self.settings, ai_profile_summaries_enabled=False)
            )
        )
        self.assertEqual(1, outcome["people"])
        self.assertEqual(1, outcome["refreshed"])
        self.assertEqual(0, outcome["failed"])
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT person_id FROM person_context_state WHERE person_id=?",
                (self.person_id,),
            ).fetchone()
        )

    def test_profile_inference_requires_exact_two_person_authored_sources(self) -> None:
        settings = replace(self.settings, history_internal_batch_messages=10)
        queue_profile_scan(self.conn, settings, int(self.person_id))
        job_id, work = claim_ai_jobs(
            self.conn,
            "profile",
            1,
            settings,
            profile_person_id=int(self.person_id),
        )[0]
        self.assertEqual([1, 2], [message.message_id for message in work.messages])
        item = {
            "kind": "important_fact",
            "title": "capability.skill: corporate documentation",
            "details": "Strongly supported by two direct statements.",
            "status": "informational",
            "owner": "other",
            "due_date": None,
            "person": "Michael",
            "company": None,
            "project_name": None,
            "amount": None,
            "currency": None,
            "confidence": 0.9,
            "source_chat_id": 100,
            "source_message_id": 1,
            "assertion_kind": "inference",
            "effective_from": None,
            "effective_to": None,
            "supporting_evidence": [
                {"source_chat_id": 100, "source_message_id": 1},
                {"source_chat_id": 100, "source_message_id": 2},
            ],
        }
        result = save_ai_success(
            self.conn,
            work,
            {"summary": "profile inference", "items": [item]},
            settings,
            lane="profile",
            job_id=job_id,
        )
        self.assertEqual(1, result.claims_inserted, result.rejection_reasons)
        self.assertEqual(0, result.inserted)
        profile = build_person_profile(self.conn, int(self.person_id))
        self.assertEqual("inference", profile["uncertain"][0]["assertion_kind"])
        self.assertEqual(2, len(profile["uncertain"][0]["evidence"]))

    def test_response_times_use_only_adjacent_direct_chat_messages(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (200,'Working group','group')"
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,0)",
            [
                (3, "2026-08-24T14:00:00+00:00", "I will check.", 1),
                (4, "2026-08-24T17:00:00+00:00", "Thank you.", 0),
                (5, "2026-09-10T17:00:00+00:00", "Too late to pair.", 1),
            ],
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media) VALUES (200,?,?,?,?,0)",
            [
                (1, "2026-08-24T13:00:00+00:00", "Group message", 0),
                (2, "2026-08-24T13:01:00+00:00", "Group reply", 1),
            ],
        )
        stats = build_person_profile(self.conn, int(self.person_id))["stats"]
        self.assertEqual(1, stats["response_times"]["my_reply_samples"])
        self.assertEqual(2.0, stats["response_times"]["my_reply_hours"])
        self.assertEqual(1, stats["response_times"]["their_reply_samples"])
        self.assertEqual(3.0, stats["response_times"]["their_reply_hours"])

    def test_renderer_shows_exact_evidence_and_stats(self) -> None:
        output = StringIO()
        show_profile(
            build_person_profile(self.conn, int(self.person_id)),
            "person",
            Console(file=output, force_terminal=False, width=160),
        )
        rendered = output.getvalue()
        self.assertIn("Identity / status", rendered)
        self.assertIn("Brief", rendered)
        self.assertIn("Needs attention", rendered)
        self.assertIn("Active threads / projects", rendered)
        self.assertIn("Relationship + memory health", rendered)
        self.assertIn("[E]", rendered)
        self.assertNotIn("100/1", rendered)
        self.assertNotIn("extractor v", rendered)

    def test_operational_overview_reuses_existing_profile_data_without_writes(
        self,
    ) -> None:
        project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Atlas',?,?)",
            ("now", "now"),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO person_project_context(person_id,project_id,status,last_activity_at,
                   confidence,updated_at) VALUES (?,?,'active','now',0.9,'now')""",
            (self.person_id, project_id),
        )
        self.conn.commit()
        before = self.conn.total_changes

        overview = build_person_profile(self.conn, int(self.person_id))["overview"]

        self.assertEqual("Michael", overview["identity"]["name"])
        self.assertTrue(overview["identity"]["direct_chat_owned"])
        self.assertIn(
            "WAITING", [item["action_state"] for item in overview["needs_attention"]]
        )
        self.assertEqual("Atlas", overview["active_threads"][0]["name"])
        self.assertEqual(
            "fresh", overview["relationship_memory_health"]["context_state"]
        )
        self.assertEqual(before, self.conn.total_changes)

    def test_contact_briefing_is_exact_evidence_only_and_actionable(self) -> None:
        now = "2026-08-24T12:00:00+00:00"
        project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Atlas',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "UPDATE tasks SET related_project_id=? WHERE related_person_id=?",
            (project_id, self.person_id),
        )
        self.conn.execute(
            """INSERT INTO person_project_context(person_id,project_id,status,last_activity_at,
                   current_summary,confidence,updated_at) VALUES (?,?,'active',?,'Documents',0.9,?)""",
            (self.person_id, project_id, now, now),
        )
        unsupported_project_id = self.conn.execute(
            "INSERT INTO projects(canonical_name,created_at,updated_at) VALUES ('Unproven',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO person_project_context(person_id,project_id,status,last_activity_at,
                   current_summary,confidence,updated_at) VALUES (?,?,'active',?,'No proof',0.9,?)""",
            (self.person_id, unsupported_project_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO conversation_open_loops(person_id,source_type,conversation_id,loop_type,
                   title,owner,status,source_chat_id,source_message_id,confidence,created_at,updated_at)
               VALUES (?,'telegram','100','question','Confirm the signing date','me','waiting',100,1,0.9,?,?)""",
            (self.person_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO context_events(event_type,title,occurred_at,observed_at,person_id,confidence,
                   source_chat_id,source_message_id,created_at)
               VALUES ('role_change','Michael changed role',?,?,?,0.9,100,1,?)""",
            (now, now, self.person_id, now),
        )
        self.conn.commit()

        self.conn.execute(
            "UPDATE messages SET date='2026-08-25T12:00:00+00:00' WHERE chat_id=100 AND message_id=2"
        )
        self.conn.commit()

        briefing = build_person_profile(self.conn, int(self.person_id))[
            "contact_briefing"
        ]
        self.assertEqual("Send documents", briefing["waiting_from_them"][0]["title"])
        self.assertEqual(
            "Confirm the signing date", briefing["waiting_from_me"][0]["title"]
        )
        self.assertEqual("Atlas", briefing["active_projects"][0]["name"])
        self.assertEqual(1, len(briefing["active_projects"]))
        self.assertEqual(
            [(100, 1)],
            [
                (item["chat_id"], item["message_id"])
                for item in briefing["active_projects"][0]["evidence"]
            ],
        )
        self.assertEqual("Michael changed role", briefing["recent_changes"][0]["title"])
        self.assertEqual(1, briefing["last_interaction"]["evidence"]["message_id"])

    def test_contact_briefing_bounds_group_context_to_exact_evidence(self) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (200,'Atlas group','group')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (200,1,100,'2026-08-26T12:00:00+00:00','Michael confirmed the Atlas role.',0,0)"""
        )
        self.conn.executemany(
            "INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media) VALUES (100,?,?,?,?,?,0)",
            [
                (
                    message_id,
                    100,
                    f"2026-09-{message_id:02d}T12:00:00+00:00",
                    f"Unlinked newer message {message_id}",
                    0,
                )
                for message_id in range(3, 15)
            ],
        )
        self.conn.executemany(
            """INSERT INTO context_events(event_type,title,occurred_at,observed_at,person_id,confidence,
                   source_chat_id,source_message_id,created_at)
               VALUES ('role_change',?,?,?, ?,0.9,200,1,?)""",
            [
                (
                    f"Michael role update {index}",
                    f"2026-08-26T12:0{index}:00+00:00",
                    f"2026-08-26T12:0{index}:00+00:00",
                    self.person_id,
                    f"2026-08-26T12:0{index}:00+00:00",
                )
                for index in range(7)
            ],
        )
        self.conn.commit()

        briefing = build_person_profile(self.conn, int(self.person_id))[
            "contact_briefing"
        ]

        self.assertEqual(
            (200, 1),
            (
                briefing["last_interaction"]["evidence"]["chat_id"],
                briefing["last_interaction"]["evidence"]["message_id"],
            ),
        )
        self.assertEqual(6, len(briefing["recent_changes"]))
        self.assertTrue(
            all(
                [(200, 1)]
                == [
                    (item["chat_id"], item["message_id"]) for item in change["evidence"]
                ]
                for change in briefing["recent_changes"]
            )
        )
        self.assertNotIn("Unlinked newer message", repr(briefing))

    def test_contact_briefing_shows_only_exact_evidence_connections(self) -> None:
        now = "2026-08-24T12:00:00+00:00"
        company_id = self.conn.execute(
            "INSERT INTO companies(canonical_name,created_at,updated_at) VALUES ('Atlas Legal',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO relationships(
                   from_type,from_id,to_type,to_id,relationship_type,valid_from,
                   confidence,source_chat_id,source_message_id,created_at,updated_at
               ) VALUES ('person',?,'company',?,'counsel',?,0.9,100,1,?,?)""",
            (self.person_id, company_id, now, now, now),
        )
        self.conn.commit()

        briefing = build_person_profile(self.conn, int(self.person_id))[
            "contact_briefing"
        ]

        self.assertEqual("Atlas Legal", briefing["connections"][0]["other_name"])
        self.assertEqual(
            [(100, 1)],
            [
                (item["chat_id"], item["message_id"])
                for item in briefing["connections"][0]["evidence"]
            ],
        )

    def test_sparse_or_ambiguous_contact_has_explicitly_unknown_briefing(self) -> None:
        now = "2026-08-24T12:00:00+00:00"
        person_id = self.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Mikhail',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO semantic_claim_entity_refs(claim_id,ordinal,role,entity_type,surface_name,
                   canonical_entity_id,resolution_status,created_at)
               VALUES (1,1,'subject','person','Mikhail',?,'review',?)""",
            (person_id, now),
        )
        self.conn.commit()

        profile = build_person_profile(self.conn, int(person_id))
        briefing = profile["contact_briefing"]
        self.assertIsNone(briefing["last_interaction"])
        self.assertFalse(briefing["waiting_from_them"])
        self.assertEqual(1, profile["identity"]["pending_reviews"])
        output = StringIO()
        show_profile(
            profile,
            "person",
            Console(file=output, force_terminal=False, width=72),
            section="contact",
        )
        self.assertIn("unknown / insufficient evidence", output.getvalue())


if __name__ == "__main__":
    unittest.main()
