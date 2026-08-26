from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.ai.claims import save_claim
from alex_memory.ai.repository import save_ai_success
from alex_memory.database import connect
from alex_memory.models import AIBatch
from test_ai_pipeline import make_settings, message, valid_item


class SemanticClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_valid_legacy_item_persists_one_immutable_claim_with_exact_evidence(
        self,
    ) -> None:
        batch = AIBatch(100, "Test chat", [message()], "prompt")

        result = save_ai_success(
            self.conn,
            batch,
            {"summary": "Invoice request.", "items": [valid_item()]},
            self.settings,
        )

        self.assertEqual(1, result.claims_inserted)
        self.assertEqual(1, len(result.saved_claim_ids))
        claim_id = result.saved_claim_ids[0]
        self.assertEqual(
            ("commitment", "observed", 0.9),
            self.conn.execute(
                "SELECT claim_type,authority_status,confidence FROM semantic_claims WHERE claim_id=?",
                (claim_id,),
            ).fetchone(),
        )
        self.assertEqual(
            [(100, 1)],
            self.conn.execute(
                """SELECT source_chat_id,source_message_id
                   FROM semantic_claim_evidence WHERE claim_id=?""",
                (claim_id,),
            ).fetchall(),
        )

    def test_claim_rejects_unknown_type_and_foreign_or_missing_evidence(self) -> None:
        valid_refs = {(100, 1)}
        base = {
            "claim_type": "event",
            "statement": "Invoice discussed",
            "payload": {},
            "confidence": 0.8,
            "evidence": [{"source_chat_id": 100, "source_message_id": 1}],
            "entity_refs": [],
        }
        for claim, expected in (
            (base | {"claim_type": "unknown"}, "invalid claim_type"),
            (
                base | {"evidence": [{"source_chat_id": 100, "source_message_id": 99}]},
                "is not in this batch",
            ),
            (base | {"evidence": []}, "must include direct evidence"),
            (base | {"confidence": float("nan")}, "finite number"),
        ):
            claim_id, inserted, reason = save_claim(
                self.conn,
                batch_id=1,
                claim=claim,
                valid_refs=valid_refs,
                provider="test",
                model="test-model",
                extractor_version=2,
                created_at="2026-08-24T10:00:00+00:00",
            )
            self.assertIsNone(claim_id)
            self.assertFalse(inserted)
            self.assertIn(expected, reason or "")
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) FROM semantic_claims").fetchone()[0]
        )

    def test_claim_migration_adds_graph_boundary_and_canonical_claim_columns(
        self,
    ) -> None:
        for table in (
            "semantic_claims",
            "semantic_claim_evidence",
            "semantic_claim_entity_refs",
            "graph_nodes",
            "graph_edges",
            "graph_edge_claims",
        ):
            self.assertIsNotNone(
                self.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone(),
                table,
            )
        for table in ("tasks", "context_events", "context_facts", "relationships"):
            columns = {
                row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            self.assertIn("source_claim_id", columns, table)
        self.assertIn(
            "source_claim_id",
            {row[1] for row in self.conn.execute("PRAGMA table_info(ai_items)")},
        )
        self.assertIn(
            "projection_status",
            {row[1] for row in self.conn.execute("PRAGMA table_info(semantic_claims)")},
        )

    def test_claim_replay_is_idempotent(self) -> None:
        batch = AIBatch(100, "Test chat", [message()], "prompt")
        payload = {"summary": "Invoice request.", "items": [valid_item()]}

        first = save_ai_success(self.conn, batch, payload, self.settings)
        second = save_ai_success(self.conn, batch, payload, self.settings)

        self.assertEqual(1, first.claims_inserted)
        self.assertEqual(1, second.claims_duplicated)
        self.assertEqual(
            1, self.conn.execute("SELECT COUNT(*) FROM semantic_claims").fetchone()[0]
        )
        self.assertEqual(
            1,
            self.conn.execute(
                "SELECT COUNT(*) FROM semantic_claim_evidence"
            ).fetchone()[0],
        )
        self.assertIsNotNone(
            self.conn.execute("SELECT source_claim_id FROM ai_items").fetchone()[0]
        )


if __name__ == "__main__":
    unittest.main()
