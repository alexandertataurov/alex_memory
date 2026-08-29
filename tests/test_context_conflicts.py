from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.context import list_temporal_conflicts, resolve_temporal_conflict
from alex_memory.context.repository import current_facts, set_temporal_fact
from alex_memory.database import connect

from test_ai_pipeline import make_settings


class TemporalConflictReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.conn = connect(make_settings(Path(self.directory.name)))
        now = "2026-08-19T10:00:00+00:00"
        self.person_id = int(
            self.conn.execute(
                "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Michael',?,?)",
                (now, now),
            ).lastrowid
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_list_and_accept_conflicting_observation_preserves_evidence(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "North"},
            valid_from="2026-08-19",
            confidence=0.8,
            source_chat_id=4,
            source_message_id=10,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "South"},
            valid_from="2026-08-22",
            confidence=0.9,
            source_chat_id=5,
            source_message_id=11,
            source_ai_item_id=7,
        )

        conflicts = list_temporal_conflicts(self.conn)
        self.assertEqual(1, len(conflicts))
        self.assertEqual({"company": "North"}, conflicts[0]["existing_value"])
        self.assertEqual({"company": "South"}, conflicts[0]["observation_value"])
        self.assertEqual(5, conflicts[0]["observation_source_chat_id"])
        self.assertEqual(11, conflicts[0]["observation_source_message_id"])

        fact_id = resolve_temporal_conflict(
            self.conn, conflicts[0]["conflict_id"], "accept_observation", "Confirmed"
        )
        self.assertIsNotNone(fact_id)
        self.assertEqual(
            {"company": "South"},
            current_facts(self.conn, "person", self.person_id)[0]["value"],
        )
        self.assertEqual(0, len(list_temporal_conflicts(self.conn)))
        self.assertEqual(
            ("accept_observation", "Confirmed", fact_id),
            self.conn.execute(
                "SELECT decision,note,resulting_fact_id FROM context_conflict_decisions"
            ).fetchone(),
        )

    def test_keep_existing_records_manual_decision_without_rewriting_fact(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="role",
            value={"title": "Director"},
            valid_from="2026-08-19",
            confidence=1,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="role",
            value={"title": "Advisor"},
            valid_from="2026-08-22",
            confidence=0.7,
        )
        conflict_id = list_temporal_conflicts(self.conn)[0]["conflict_id"]

        self.assertIsNone(
            resolve_temporal_conflict(self.conn, conflict_id, "keep_existing")
        )
        self.assertEqual(
            {"title": "Director"},
            current_facts(self.conn, "person", self.person_id)[0]["value"],
        )
        self.assertEqual(
            "resolved",
            self.conn.execute(
                "SELECT status FROM context_conflicts WHERE conflict_id=?",
                (conflict_id,),
            ).fetchone()[0],
        )

    def test_legacy_conflict_without_observation_accepts_manual_correction(
        self,
    ) -> None:
        fact_id = set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="location",
            value={"city": "Tbilisi"},
            valid_from="2026-08-19",
            confidence=1,
        )
        self.conn.execute(
            """INSERT INTO context_conflicts(subject_type,subject_id,predicate,existing_fact_id,
               conflict_type,status,created_at) VALUES ('person',?,?,?,'value_conflict','pending',?)""",
            (self.person_id, "location", fact_id, "2026-08-22T00:00:00+00:00"),
        )
        conflict = list_temporal_conflicts(self.conn)[0]
        self.assertIsNone(conflict["observation_value"])
        resulting_fact_id = resolve_temporal_conflict(
            self.conn,
            conflict["conflict_id"],
            "accept_observation",
            "Corrected manually",
            manual_value={"city": "Batumi"},
            manual_valid_from="2026-08-22",
        )
        self.assertIsNotNone(resulting_fact_id)
        fact = current_facts(self.conn, "person", self.person_id)[0]
        self.assertEqual({"city": "Batumi"}, fact["value"])
        self.assertEqual(
            "manual",
            self.conn.execute(
                "SELECT source_type FROM context_facts WHERE fact_id=?",
                (resulting_fact_id,),
            ).fetchone()[0],
        )

    def test_status_name_does_not_grant_automatic_replacement(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="document_status",
            value={"status": "requested"},
            valid_from="2026-08-19",
            confidence=0.8,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="document_status",
            value={"status": "received"},
            valid_from="2026-08-22",
            confidence=0.9,
            source_chat_id=5,
            source_message_id=11,
        )

        self.assertEqual(
            {"status": "requested"},
            current_facts(self.conn, "person", self.person_id)[0]["value"],
        )
        self.assertEqual(1, len(list_temporal_conflicts(self.conn)))

    def test_duplicate_conflict_observation_replay_is_idempotent(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "North"},
            valid_from="2026-08-19",
            confidence=0.8,
        )
        observation = dict(
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "South"},
            valid_from="2026-08-22",
            confidence=0.9,
            source_chat_id=5,
            source_message_id=11,
        )
        set_temporal_fact(self.conn, **observation)
        set_temporal_fact(self.conn, **observation)

        self.assertEqual(1, len(list_temporal_conflicts(self.conn)))
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM context_conflict_observations"
            ).fetchone()[0],
        )

    def test_stale_conflict_cannot_replace_newer_current_fact(self) -> None:
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "North"},
            valid_from="2026-08-19",
            confidence=0.8,
        )
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "South"},
            valid_from="2026-08-22",
            confidence=0.9,
            source_chat_id=5,
            source_message_id=11,
        )
        conflict_id = list_temporal_conflicts(self.conn)[0]["conflict_id"]
        set_temporal_fact(
            self.conn,
            subject_type="person",
            subject_id=self.person_id,
            predicate="employment",
            value={"company": "East"},
            valid_from="2026-08-23",
            confidence=1.0,
            conflict_policy="replace",
        )
        self.conn.commit()

        with self.assertRaisesRegex(ValueError, "stale"):
            resolve_temporal_conflict(self.conn, conflict_id, "accept_observation")
        self.assertEqual(
            {"company": "East"},
            current_facts(self.conn, "person", self.person_id)[0]["value"],
        )
