from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.database import connect
from alex_memory.person_profile import build_person_profile, profile_summary_package

from test_ai_pipeline import make_settings


class PersonIntelligenceBenchmarkTests(unittest.TestCase):
    """Small synthetic contract fixture for the primary Person read model."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.conn = connect(make_settings(Path(self.directory.name)))
        now = "2026-08-24T12:00:00+00:00"
        self.person_id = self.conn.execute(
            """INSERT INTO people(canonical_name,telegram_user_id,created_at,updated_at)
               VALUES ('Mikhail',100,?,?)""",
            (now, now),
        ).lastrowid
        self.company_id = self.conn.execute(
            "INSERT INTO companies(canonical_name,created_at,updated_at) VALUES ('Atlas',?,?)",
            (now, now),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO entity_aliases(entity_type,entity_id,alias,normalized_alias,created_at) VALUES ('person',?,'Michael','michael',?)",
            (self.person_id, now),
        )
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Mikhail','user')"
        )
        self.conn.executemany(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing,has_media)
               VALUES (100,?,?,?,?,?,0)""",
            [
                (
                    1,
                    100,
                    "2026-08-01T12:00:00+00:00",
                    "I am now legal lead at Atlas.",
                    0,
                ),
                (2, 100, "2026-08-24T12:00:00+00:00", "Please send the contract.", 0),
                (3, 100, "2026-08-24T12:01:00+00:00", "Unrelated later message.", 0),
            ],
        )
        self.claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,extractor_version,
               provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (1,'temporal_fact','Role','{}',1,'test','test',1,'accepted','benchmark-role',?)""",
            (now,),
        ).lastrowid
        self.conn.execute(
            "INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,source_message_id,created_at) VALUES (?,0,100,1,?)",
            (self.claim_id, now),
        )
        current_fact_id = self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               observed_at,is_current,confidence,source_claim_id,created_at,updated_at)
               VALUES ('person',?,'professional.role','\"Legal lead\"',?, ?,1,1,?,?,?)""",
            (self.person_id, now, now, self.claim_id, now, now),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               valid_to,is_current,superseded_by_fact_id,observed_at,confidence,source_claim_id,
               created_at,updated_at)
               VALUES ('person',?,'professional.role','\"Counsel\"','2026-07-01T12:00:00+00:00',
                       ?,0,?,?,1,?,?,?)""",
            (self.person_id, now, current_fact_id, now, self.claim_id, now, now),
        )
        unsupported_claim_id = self.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,extractor_version,
               provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (1,'temporal_fact','Unsupported','{}',1,'test','test',1,'accepted','benchmark-unsupported',?)""",
            (now,),
        ).lastrowid
        self.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,valid_from,
               observed_at,is_current,confidence,source_claim_id,created_at,updated_at)
               VALUES ('person',?,'capability','\"Unproven\"',?, ?,1,1,?,?,?)""",
            (self.person_id, now, now, unsupported_claim_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,source_chat_id,
               confidence,source_claim_id,created_at,updated_at)
               VALUES ('Send contract','send contract','waiting','other',?,100,1,?,?,?)""",
            (self.person_id, self.claim_id, now, now),
        )
        self.conn.execute(
            """INSERT INTO relationships(from_type,from_id,to_type,to_id,relationship_type,valid_from,
               confidence,source_chat_id,source_message_id,created_at,updated_at)
               VALUES ('person',?,'company',?,'works_for',?,1,100,1,?,?)""",
            (self.person_id, self.company_id, now, now, now),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_synthetic_person_intelligence_contract(self) -> None:
        before = self.conn.total_changes
        profile = build_person_profile(self.conn, int(self.person_id))
        package = profile_summary_package(self.conn, int(self.person_id))

        self.assertEqual(before, self.conn.total_changes)
        self.assertEqual("Mikhail", profile["entity"][1])
        self.assertTrue(profile["identity"]["direct_chat_owned"])
        self.assertEqual(["Michael"], profile["aliases"])
        self.assertEqual(
            [("Legal lead", "Now"), ("Counsel", "Previously")],
            [
                (fact["display_value"], fact["temporal_state"])
                for fact in profile["facts"]
                if fact["predicate"] == "professional.role"
            ],
        )
        self.assertNotIn(
            "Unproven", [fact["display_value"] for fact in profile["facts"]]
        )
        self.assertEqual(
            ["Send contract"], [task["title"] for task in profile["tasks"]]
        )
        self.assertEqual(
            [("company", int(self.company_id), "Atlas")],
            [
                (
                    relationship["other_type"],
                    relationship["other_id"],
                    relationship["other_name"],
                )
                for relationship in profile["relationships"]
            ],
        )
        self.assertEqual(
            [(100, 1)],
            [(item["chat_id"], item["message_id"]) for item in package["sources"]],
        )
        self.assertEqual(1, len(package["sources"]))
